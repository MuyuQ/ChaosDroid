"""设备隔离与恢复服务。"""

import logging
from datetime import datetime, timezone
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from chaosdroid.models import Device, IncidentEvent
from chaosdroid.scheduling.enums import DeviceStatus, EventType, EventSeverity

logger = logging.getLogger(__name__)


class QuarantineService:
    """设备隔离与恢复服务。"""

    def __init__(self, session: Session):
        self.session = session

    def quarantine_device(
        self,
        device: Device,
        reason: str,
        severity: EventSeverity = EventSeverity.WARNING,
    ) -> bool:
        """
        隔离设备。

        Args:
            device: 要隔离的设备
            reason: 隔离原因
            severity: 事件严重程度

        Returns:
            是否成功隔离（已隔离的设备返回False）
        """
        # 如果设备已被隔离，返回False
        if device.status == DeviceStatus.QUARANTINED.value:
            logger.warning(f"设备 {device.serial} 已处于隔离状态")
            return False

        # 设置设备状态为隔离
        device.status = DeviceStatus.QUARANTINED.value
        device.quarantine_reason = reason

        # 创建隔离事件
        event = IncidentEvent(
            device_id=device.id,
            event_type=EventType.DEVICE_QUARANTINED.value,
            severity=severity.value,
            payload_json={
                "device_serial": device.serial,
                "reason": reason,
                "previous_status": device.status,
                "quarantined_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        self.session.add(event)

        self.session.flush()
        logger.info(f"设备 {device.serial} 已隔离: {reason}")
        return True

    def recover_device(
        self,
        device: Device,
        reason: str = "Manual recovery",
    ) -> bool:
        """
        恢复设备。

        Args:
            device: 要恢复的设备
            reason: 恢复原因

        Returns:
            是否成功恢复（未隔离的设备返回False）
        """
        # 如果设备未被隔离，返回False
        if device.status != DeviceStatus.QUARANTINED.value:
            logger.warning(f"设备 {device.serial} 未处于隔离状态")
            return False

        # 恢复设备状态
        device.status = DeviceStatus.IDLE.value
        device.quarantine_reason = None
        device.sync_failure_count = 0

        # 创建恢复事件
        event = IncidentEvent(
            device_id=device.id,
            event_type=EventType.DEVICE_RECOVERED.value,
            severity=EventSeverity.INFO.value,
            payload_json={
                "device_serial": device.serial,
                "reason": reason,
                "recovered_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        self.session.add(event)

        self.session.flush()
        logger.info(f"设备 {device.serial} 已恢复: {reason}")
        return True

    def get_quarantined_devices(self) -> List[Device]:
        """
        获取隔离设备列表。

        Returns:
            处于隔离状态的设备列表
        """
        stmt = select(Device).where(
            Device.status == DeviceStatus.QUARANTINED.value
        )
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def check_and_quarantine(self, max_sync_failures: int = 3) -> int:
        """
        检查并隔离异常设备。

        扫描所有同步失败次数超过阈值的设备，并自动隔离。

        Args:
            max_sync_failures: 最大允许的同步失败次数

        Returns:
            被隔离的设备数量
        """
        # 查找需要隔离的设备
        stmt = select(Device).where(
            Device.sync_failure_count >= max_sync_failures,
            Device.status != DeviceStatus.QUARANTINED.value,
        )
        result = self.session.execute(stmt)
        devices_to_quarantine = list(result.scalars().all())

        quarantined_count = 0
        for device in devices_to_quarantine:
            reason = f"同步失败次数超过阈值 ({device.sync_failure_count}/{max_sync_failures})"
            success = self.quarantine_device(
                device,
                reason,
                severity=EventSeverity.ERROR,
            )
            if success:
                quarantined_count += 1

        if quarantined_count > 0:
            logger.info(f"已自动隔离 {quarantined_count} 个异常设备")

        return quarantined_count