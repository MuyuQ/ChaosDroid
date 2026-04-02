"""设备租约管理服务."""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.device_lease import DeviceLease
from app.models.scenario import ScenarioRun
from app.models.event import IncidentEvent
from app.scheduling.enums import DeviceStatus, LeaseStatus, EventType, EventSeverity
from app.models.base import RunStatus

logger = logging.getLogger(__name__)


class LeaseManager:
    """设备租约管理服务.

    管理设备租约的生命周期，包括创建、释放和抢占操作。
    """

    def __init__(self, session: Session):
        """初始化租约管理器.

        Args:
            session: SQLAlchemy 数据库会话
        """
        self.session = session

    def create_lease(
        self,
        device: Device,
        run: ScenarioRun,
        preemptible: bool = True,
        expires_at: Optional[datetime] = None,
    ) -> DeviceLease:
        """创建设备租约.

        Args:
            device: 要租用的设备
            run: 场景执行记录
            preemptible: 是否可被抢占
            expires_at: 租约过期时间（可选）

        Returns:
            创建的设备租约
        """
        now = datetime.now(timezone.utc)

        # 创建设备租约
        lease = DeviceLease(
            device_id=device.id,
            scenario_run_id=run.id,
            lease_status=LeaseStatus.ACTIVE.value,
            leased_at=now,
            expires_at=expires_at,
            preemptible=preemptible,
        )
        self.session.add(lease)
        self.session.flush()  # 刷新以获取 lease.id

        # 更新设备状态为 RESERVED
        device.status = DeviceStatus.RESERVED.value

        # 更新场景执行记录的设备和租约信息
        run.status = RunStatus.RESERVED.value
        run.device_id = device.id
        run.lease_id = lease.id  # 现在 lease.id 已可用
        run.allocated_at = now

        # 创建租约创建事件
        event = IncidentEvent(
            device_id=device.id,
            scenario_run_id=run.id,
            event_type=EventType.LEASE_CREATED.value,
            severity=EventSeverity.INFO.value,
            payload_json={
                "device_serial": device.serial,
                "preemptible": preemptible,
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
        )
        self.session.add(event)

        self.session.commit()

        logger.info(
            f"创建租约: lease_id={lease.id}, device_id={device.id}, "
            f"run_id={run.id}, preemptible={preemptible}"
        )

        return lease

    def release_lease(self, lease: DeviceLease) -> bool:
        """释放设备租约.

        Args:
            lease: 要释放的租约

        Returns:
            是否成功释放租约
        """
        # 检查租约状态
        if lease.lease_status != LeaseStatus.ACTIVE.value:
            logger.warning(
                f"租约已非活跃状态，无法释放: lease_id={lease.id}, "
                f"status={lease.lease_status}"
            )
            return False

        now = datetime.now(timezone.utc)

        # 更新租约状态
        lease.lease_status = LeaseStatus.RELEASED.value
        lease.released_at = now

        # 获取关联的设备并更新状态为 IDLE
        device = self.session.get(Device, lease.device_id)
        if device:
            device.status = DeviceStatus.IDLE.value

        self.session.commit()

        logger.info(
            f"释放租约: lease_id={lease.id}, device_id={lease.device_id}"
        )

        return True

    def preempt_lease(
        self,
        old_lease: DeviceLease,
        new_run: ScenarioRun,
    ) -> DeviceLease:
        """抢占租约.

        将现有租约标记为被抢占，并为新的场景执行创建新租约。

        Args:
            old_lease: 要抢占的旧租约
            new_run: 新的场景执行记录

        Returns:
            新创建的设备租约
        """
        now = datetime.now(timezone.utc)

        # 标记旧租约为被抢占
        old_lease.lease_status = LeaseStatus.PREEMPTED.value
        old_lease.released_at = now

        # 获取关联的设备和旧的执行记录
        device = self.session.get(Device, old_lease.device_id)
        old_run = self.session.get(ScenarioRun, old_lease.scenario_run_id)

        # 创建新租约（紧急任务租约不可被抢占）
        new_lease = DeviceLease(
            device_id=device.id if device else old_lease.device_id,
            scenario_run_id=new_run.id,
            lease_status=LeaseStatus.ACTIVE.value,
            leased_at=now,
            preemptible=False,  # 紧急任务租约不可被抢占
        )
        self.session.add(new_lease)
        self.session.flush()  # 刷新以获取 new_lease.id

        # 更新新的场景执行记录
        if device:
            new_run.device_id = device.id
            new_run.status = RunStatus.RESERVED.value
        new_run.lease_id = new_lease.id  # 现在 new_lease.id 已可用
        new_run.allocated_at = now

        # 更新旧执行记录的状态
        if old_run:
            old_run.status = RunStatus.PREEMPTED.value
            old_run.preempted_at = now
            old_run.preempted_by_run_id = new_run.id

        # 创建抢占事件
        event = IncidentEvent(
            device_id=device.id if device else old_lease.device_id,
            scenario_run_id=new_run.id,
            event_type=EventType.PREEMPTION_TRIGGERED.value,
            severity=EventSeverity.WARNING.value,
            payload_json={
                "old_lease_id": old_lease.id,
                "old_run_id": old_lease.scenario_run_id,
                "new_run_id": new_run.id,
                "device_serial": device.serial if device else None,
            },
        )
        self.session.add(event)

        self.session.commit()

        logger.warning(
            f"抢占租约: old_lease_id={old_lease.id}, "
            f"new_lease_id={new_lease.id}, new_run_id={new_run.id}, "
            f"device_id={old_lease.device_id}"
        )

        return new_lease

    def get_active_lease(self, device_id: int) -> Optional[DeviceLease]:
        """获取设备的活跃租约.

        Args:
            device_id: 设备ID

        Returns:
            活跃的租约，如果不存在则返回 None
        """
        stmt = select(DeviceLease).where(
            DeviceLease.device_id == device_id,
            DeviceLease.lease_status == LeaseStatus.ACTIVE.value,
        )
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()

    def get_run_lease(self, run_id: int) -> Optional[DeviceLease]:
        """获取场景执行的租约.

        Args:
            run_id: 场景执行记录ID

        Returns:
            关联的租约，如果不存在则返回 None
        """
        stmt = select(DeviceLease).where(DeviceLease.scenario_run_id == run_id)
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()

    def get_preemptable_leases(
        self,
        pool_id: Optional[int] = None,
    ) -> list[DeviceLease]:
        """获取可抢占的租约列表.

        筛选条件：活跃状态、可抢占、关联任务为interruptible。

        Args:
            pool_id: 设备池ID（可选，用于筛选特定池的租约）

        Returns:
            可抢占的租约列表
        """
        # 使用显式join条件避免多外键歧义
        stmt = select(DeviceLease).join(
            ScenarioRun,
            DeviceLease.scenario_run_id == ScenarioRun.id,
        ).where(
            and_(
                DeviceLease.lease_status == LeaseStatus.ACTIVE.value,
                DeviceLease.preemptible == True,
                ScenarioRun.interruptible == True,
            )
        )

        if pool_id is not None:
            # 通过设备关联筛选设备池
            stmt = stmt.join(Device).where(Device.pool_id == pool_id)

        result = self.session.execute(stmt)
        return list(result.scalars().all())