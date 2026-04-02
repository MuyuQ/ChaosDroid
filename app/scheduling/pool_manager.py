"""设备池管理服务.

提供设备池管理、设备选择和容量计算功能。
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.device_pool import DevicePool
from app.scheduling.enums import DeviceStatus, DevicePoolPurpose

logger = logging.getLogger(__name__)


class PoolManager:
    """设备池管理服务.

    提供设备池的创建、查询和设备选择功能。
    支持基于健康分数、标签和状态的设备筛选。
    """

    def __init__(self, session: Session):
        """初始化设备池管理服务.

        Args:
            session: 数据库会话
        """
        self.session = session

    def get_candidate_devices(
        self,
        pool_id: Optional[int] = None,
        min_health: int = 40,
        required_tags: Optional[List[str]] = None,
        exclude_offline: bool = True,
    ) -> List[Device]:
        """获取候选设备列表.

        根据条件筛选可用于执行任务的设备。

        Args:
            pool_id: 设备池ID，如果指定则只返回该池内的设备
            min_health: 最低健康分数阈值，默认40
            required_tags: 设备必须包含的标签列表
            exclude_offline: 是否排除离线设备，默认True

        Returns:
            符合条件的候选设备列表
        """
        # 构建基础查询：状态为idle且健康分满足要求
        conditions = [
            Device.status == DeviceStatus.IDLE.value,
            Device.health_score >= min_health,
        ]

        # 如果指定了设备池ID，添加过滤条件
        if pool_id is not None:
            conditions.append(Device.pool_id == pool_id)

        # 如果需要排除离线设备，添加过滤条件（冗余但保险）
        if exclude_offline:
            conditions.append(Device.status != DeviceStatus.OFFLINE.value)

        # 执行查询
        stmt = select(Device).where(and_(*conditions))
        result = self.session.execute(stmt)
        devices = list(result.scalars().all())

        # 如果有标签要求，进行标签过滤
        if required_tags:
            filtered_devices = []
            for device in devices:
                if device.tags_json:
                    try:
                        device_tags = json.loads(device.tags_json)
                        if isinstance(device_tags, list):
                            # 检查设备是否包含所有必需标签
                            if all(tag in device_tags for tag in required_tags):
                                filtered_devices.append(device)
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(
                            f"设备 {device.serial} 的标签JSON解析失败: {device.tags_json}"
                        )
            devices = filtered_devices

        logger.debug(
            f"获取候选设备: pool_id={pool_id}, min_health={min_health}, "
            f"required_tags={required_tags}, exclude_offline={exclude_offline}, "
            f"found={len(devices)}"
        )
        return devices

    def select_best_device(self, candidates: List[Device]) -> Optional[Device]:
        """选择最佳设备.

        从候选设备中选择健康分数最高且空闲时间最长的设备。
        排序规则：健康分数降序，最后在线时间升序（越早离线表示空闲越久）。

        Args:
            candidates: 候选设备列表

        Returns:
            最佳设备，如果列表为空则返回None
        """
        if not candidates:
            return None

        # 按健康分数降序、最后在线时间升序排序
        sorted_devices = sorted(
            candidates,
            key=lambda d: (
                -d.health_score,  # 健康分数降序
                d.last_seen_at or datetime.min.replace(tzinfo=timezone.utc),  # 空闲时间升序
            ),
        )

        best_device = sorted_devices[0]
        logger.debug(
            f"选择最佳设备: serial={best_device.serial}, "
            f"health_score={best_device.health_score}, "
            f"last_seen_at={best_device.last_seen_at}"
        )
        return best_device

    def get_available_capacity(self, pool: DevicePool) -> int:
        """获取设备池可用容量.

        计算设备池中可用于执行任务的设备数量。
        可用容量 = 空闲设备数 - (总设备数 * 预留比例)

        Args:
            pool: 设备池实例

        Returns:
            可用容量，最小为0
        """
        # 查询设备池中的空闲设备数量
        idle_stmt = select(func.count()).select_from(Device).where(
            and_(
                Device.pool_id == pool.id,
                Device.status == DeviceStatus.IDLE.value,
            )
        )
        idle_result = self.session.execute(idle_stmt)
        idle_count = idle_result.scalar() or 0

        # 查询设备池中的总设备数量
        total_stmt = select(func.count()).select_from(Device).where(
            Device.pool_id == pool.id
        )
        total_result = self.session.execute(total_stmt)
        total_count = total_result.scalar() or 0

        # 计算预留设备数量
        reserved = int(total_count * pool.reserved_emergency_ratio)

        # 计算可用容量
        available = max(0, idle_count - reserved)

        logger.debug(
            f"设备池容量: pool={pool.name}, idle={idle_count}, "
            f"total={total_count}, reserved={reserved}, available={available}"
        )
        return available

    def create_pool(
        self,
        name: str,
        purpose: str,
        reserved_emergency_ratio: float = 0.2,
        max_parallel_jobs: Optional[int] = None,
        tag_selector: Optional[dict] = None,
        enabled: bool = True,
    ) -> DevicePool:
        """创建设备池.

        Args:
            name: 设备池名称，必须唯一
            purpose: 用途类型，取值: stable/stress/emergency
            reserved_emergency_ratio: 预留应急任务比例，默认0.2
            max_parallel_jobs: 最大并行任务数，None表示不限制
            tag_selector: 设备标签选择器
            enabled: 是否启用，默认True

        Returns:
            创建的设备池实例

        Raises:
            ValueError: 如果purpose值无效
        """
        # 验证purpose值
        valid_purposes = [p.value for p in DevicePoolPurpose]
        if purpose not in valid_purposes:
            raise ValueError(
                f"无效的purpose值: {purpose}，有效值为: {valid_purposes}"
            )

        pool = DevicePool(
            name=name,
            purpose=purpose,
            reserved_emergency_ratio=reserved_emergency_ratio,
            max_parallel_jobs=max_parallel_jobs,
            tag_selector_json=tag_selector,
            enabled=enabled,
        )
        self.session.add(pool)
        self.session.flush()

        logger.info(
            f"创建设备池: id={pool.id}, name={name}, purpose={purpose}, "
            f"reserved_ratio={reserved_emergency_ratio}"
        )
        return pool

    def get_pool(self, pool_id: int) -> Optional[DevicePool]:
        """获取设备池.

        Args:
            pool_id: 设备池ID

        Returns:
            设备池实例，如果不存在则返回None
        """
        stmt = select(DevicePool).where(DevicePool.id == pool_id)
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()

    def get_pool_by_name(self, name: str) -> Optional[DevicePool]:
        """根据名称获取设备池.

        Args:
            name: 设备池名称

        Returns:
            设备池实例，如果不存在则返回None
        """
        stmt = select(DevicePool).where(DevicePool.name == name)
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()

    def list_pools(self, enabled_only: bool = True) -> List[DevicePool]:
        """列出设备池.

        Args:
            enabled_only: 是否只返回启用的设备池，默认True

        Returns:
            设备池列表
        """
        conditions = []
        if enabled_only:
            conditions.append(DevicePool.enabled == True)

        if conditions:
            stmt = select(DevicePool).where(and_(*conditions))
        else:
            stmt = select(DevicePool)

        stmt = stmt.order_by(DevicePool.id)
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def update_pool(
        self,
        pool_id: int,
        name: Optional[str] = None,
        purpose: Optional[str] = None,
        reserved_emergency_ratio: Optional[float] = None,
        max_parallel_jobs: Optional[int] = None,
        tag_selector: Optional[dict] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[DevicePool]:
        """更新设备池.

        Args:
            pool_id: 设备池ID
            name: 新名称
            purpose: 新用途
            reserved_emergency_ratio: 新预留比例
            max_parallel_jobs: 新最大并行任务数
            tag_selector: 新标签选择器
            enabled: 新启用状态

        Returns:
            更新后的设备池实例，如果不存在则返回None

        Raises:
            ValueError: 如果purpose值无效
        """
        pool = self.get_pool(pool_id)
        if pool is None:
            return None

        if name is not None:
            pool.name = name
        if purpose is not None:
            valid_purposes = [p.value for p in DevicePoolPurpose]
            if purpose not in valid_purposes:
                raise ValueError(
                    f"无效的purpose值: {purpose}，有效值为: {valid_purposes}"
                )
            pool.purpose = purpose
        if reserved_emergency_ratio is not None:
            pool.reserved_emergency_ratio = reserved_emergency_ratio
        if max_parallel_jobs is not None:
            pool.max_parallel_jobs = max_parallel_jobs
        if tag_selector is not None:
            pool.tag_selector_json = tag_selector
        if enabled is not None:
            pool.enabled = enabled

        self.session.flush()
        logger.info(f"更新设备池: id={pool_id}")
        return pool

    def delete_pool(self, pool_id: int) -> bool:
        """删除设备池.

        Args:
            pool_id: 设备池ID

        Returns:
            是否成功删除
        """
        pool = self.get_pool(pool_id)
        if pool is None:
            return False

        self.session.delete(pool)
        self.session.flush()
        logger.info(f"删除设备池: id={pool_id}")
        return True