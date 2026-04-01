"""设备同步服务。

提供设备状态同步和健康评分计算功能。
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from chaosdroid.models.device import Device
from chaosdroid.scheduling.enums import DeviceStatus
from chaosdroid.executors.mock_executor import MockDeviceExecutor

logger = logging.getLogger(__name__)


class DeviceSyncService:
    """设备状态同步服务.

    负责同步设备状态、计算健康评分和管理设备信息更新。
    """

    def __init__(self, session: Session, executor_mode: str = "mock"):
        """初始化设备同步服务.

        Args:
            session: 数据库会话
            executor_mode: 执行器模式 ("mock" 或 "real")
        """
        self.session = session
        self.executor_mode = executor_mode

    def calculate_health_score(self, device: Device) -> int:
        """计算设备健康评分 (0-100).

        评分规则:
        - 在线状态: +40分 (非offline/quarantined)
        - 电池电量 > 30%: +20分
        - 正常状态: +10分 (非quarantined/recovering)
        - 无同步失败: +10分

        Args:
            device: 设备对象

        Returns:
            健康评分 (0-100)
        """
        score = 0

        # 在线检查: 非offline/quarantined状态得40分
        if device.status not in [DeviceStatus.OFFLINE.value, DeviceStatus.QUARANTINED.value]:
            score += 40

        # 电池电量 > 30%: 得20分
        if device.battery_level is not None and device.battery_level > 30:
            score += 20

        # 正常状态: 非quarantined/recovering状态得10分
        if device.status not in [DeviceStatus.QUARANTINED.value, DeviceStatus.RECOVERING.value]:
            score += 10

        # 无同步失败: 得10分
        if device.sync_failure_count == 0:
            score += 10

        # 确保分数在0-100范围内
        return min(100, max(0, score))

    def sync_device(self, serial: str) -> Optional[Device]:
        """同步单个设备状态.

        获取或创建设备，更新其状态信息并计算健康评分。

        Args:
            serial: 设备序列号

        Returns:
            更新后的设备对象，如果同步失败则返回None
        """
        try:
            # 查找或创建设备
            stmt = select(Device).where(Device.serial == serial)
            result = self.session.execute(stmt)
            device = result.scalar_one_or_none()

            if device is None:
                # 创建新设备
                device = Device(
                    serial=serial,
                    status=DeviceStatus.IDLE.value,
                    executor_mode=self.executor_mode,
                )
                self.session.add(device)

            # 获取执行器并同步状态
            executor = self._get_executor(serial)

            # 在mock模式下设置默认状态
            if self.executor_mode == "mock":
                device.status = DeviceStatus.IDLE.value
                device.battery_level = 80

            # 计算健康评分
            device.health_score = self.calculate_health_score(device)

            # 更新最后在线时间
            device.last_seen_at = datetime.now(timezone.utc)

            # 重置同步失败计数
            device.sync_failure_count = 0

            self.session.commit()
            logger.info(f"设备同步成功: {serial}, 健康评分: {device.health_score}")

            return device

        except Exception as e:
            logger.error(f"设备同步失败: {serial}, 错误: {e}")
            self.session.rollback()

            # 增加同步失败计数
            try:
                stmt = select(Device).where(Device.serial == serial)
                result = self.session.execute(stmt)
                device = result.scalar_one_or_none()
                if device:
                    device.sync_failure_count += 1
                    self.session.commit()
            except Exception:
                self.session.rollback()

            return None

    async def sync_all(self) -> int:
        """同步所有设备状态.

        遍历所有已知设备并更新其状态。

        Returns:
            成功同步的设备数量
        """
        try:
            # 获取所有设备
            stmt = select(Device)
            result = self.session.execute(stmt)
            devices = result.scalars().all()

            success_count = 0
            for device in devices:
                synced_device = self.sync_device(device.serial)
                if synced_device is not None:
                    success_count += 1

            logger.info(f"批量设备同步完成: {success_count}/{len(devices)} 成功")
            return success_count

        except Exception as e:
            logger.error(f"批量设备同步失败: {e}")
            return 0

    def _get_executor(self, serial: str):
        """获取设备执行器.

        根据执行器模式返回对应的执行器实例。

        Args:
            serial: 设备序列号

        Returns:
            设备执行器实例
        """
        if self.executor_mode == "mock":
            return MockDeviceExecutor(serial)
        else:
            # 真实模式下返回真实执行器
            # 此处可以扩展支持RealDeviceExecutor
            logger.warning(f"真实执行器模式尚未实现，使用mock执行器: {serial}")
            return MockDeviceExecutor(serial)