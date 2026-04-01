"""任务调度器服务.

提供任务调度功能，包括设备分配和任务抢占。
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, and_, case
from sqlalchemy.orm import Session

from chaosdroid.models.device import Device
from chaosdroid.models.device_lease import DeviceLease
from chaosdroid.models.scenario import ScenarioRun
from chaosdroid.models.base import RunStatus
from chaosdroid.scheduling.enums import Priority, LeaseStatus
from chaosdroid.scheduling.pool_manager import PoolManager
from chaosdroid.scheduling.lease_manager import LeaseManager

logger = logging.getLogger(__name__)

# 优先级值映射（越高越重要）
PRIORITY_VALUE = {
    Priority.NORMAL.value: 1,
    Priority.HIGH.value: 2,
    Priority.EMERGENCY.value: 3,
}


class Scheduler:
    """任务调度器.

    负责将排队中的任务分配到可用设备。
    支持优先级排序和紧急任务抢占机制。
    """

    def __init__(self, session: Session):
        """初始化调度器.

        Args:
            session: 数据库会话
        """
        self.session = session
        self.pool_manager = PoolManager(session)
        self.lease_manager = LeaseManager(session)

    def schedule_once(self) -> int:
        """执行一次调度循环.

        查询所有排队中的任务，按优先级和时间排序，
        尝试为每个任务分配设备。

        Returns:
            成功分配的任务数量
        """
        # 查询所有排队中的任务
        stmt = select(ScenarioRun).where(
            ScenarioRun.status == RunStatus.QUEUED.value
        )

        # 使用 CASE 表达式按优先级值排序（emergency=3 > high=2 > normal=1）
        priority_order = case(
            (ScenarioRun.priority == Priority.EMERGENCY.value, 3),
            (ScenarioRun.priority == Priority.HIGH.value, 2),
            (ScenarioRun.priority == Priority.NORMAL.value, 1),
            else_=0,
        )

        # 按优先级降序、提交时间升序排序
        stmt = stmt.order_by(
            priority_order.desc(),
            ScenarioRun.submitted_at.asc(),
        )

        result = self.session.execute(stmt)
        queued_runs = list(result.scalars().all())

        if not queued_runs:
            logger.debug("没有排队中的任务")
            return 0

        allocated_count = 0

        for run in queued_runs:
            success = self._try_allocate(run)

            if success:
                allocated_count += 1
                logger.info(
                    f"任务分配成功: run_id={run.id}, "
                    f"priority={run.priority}, device_id={run.device_id}"
                )

        logger.info(f"调度完成: 总排队={len(queued_runs)}, 成功分配={allocated_count}")

        return allocated_count

    def _try_allocate(self, run: ScenarioRun) -> bool:
        """尝试为任务分配设备.

        Args:
            run: 场景执行记录

        Returns:
            是否成功分配
        """
        # 获取候选设备
        candidates = self.pool_manager.get_candidate_devices(
            pool_id=run.device_pool_id,
            min_health=40,
        )

        if candidates:
            # 选择最佳设备并分配
            best_device = self.pool_manager.select_best_device(candidates)
            if best_device:
                return self._allocate_device(best_device, run)

        # 如果没有候选设备且任务为紧急优先级，尝试抢占
        if run.priority == Priority.EMERGENCY.value:
            return self._try_preempt(run)

        logger.debug(
            f"无法分配任务: run_id={run.id}, priority={run.priority}, "
            f"candidates={len(candidates)}"
        )

        return False

    def _allocate_device(
        self,
        device: Device,
        run: ScenarioRun,
    ) -> bool:
        """分配设备给任务.

        创建租约并更新任务状态。

        Args:
            device: 要分配的设备
            run: 场景执行记录

        Returns:
            是否成功分配
        """
        try:
            # 创建租约（根据任务interruptible设置preemptible）
            lease = self.lease_manager.create_lease(
                device=device,
                run=run,
                preemptible=run.interruptible,
            )

            logger.info(
                f"设备分配成功: device_id={device.id}, "
                f"serial={device.serial}, run_id={run.id}, "
                f"lease_id={lease.id}"
            )

            return True

        except Exception as e:
            logger.error(
                f"设备分配失败: device_id={device.id}, "
                f"run_id={run.id}, error={e}"
            )
            return False

    def _try_preempt(self, emergency_run: ScenarioRun) -> bool:
        """尝试抢占任务（仅用于紧急任务）.

        查找可抢占的租约，选择一个进行抢占，
        将设备重新分配给紧急任务。

        Args:
            emergency_run: 紧急任务

        Returns:
            是否成功抢占
        """
        # 获取可抢占的租约
        preemptable_leases = self.lease_manager.get_preemptable_leases(
            pool_id=emergency_run.device_pool_id,
        )

        if not preemptable_leases:
            logger.warning(
                f"无法抢占: 没有可抢占的租约, "
                f"run_id={emergency_run.id}, pool_id={emergency_run.device_pool_id}"
            )
            return False

        # 选择一个可抢占的租约进行抢占
        # 优先抢占提交时间最早的normal任务
        for lease in preemptable_leases:
            # 获取关联的任务，检查优先级
            stmt = select(ScenarioRun).where(
                ScenarioRun.id == lease.scenario_run_id,
            )
            result = self.session.execute(stmt)
            target_run = result.scalar_one_or_none()

            # 只抢占normal优先级的任务
            if target_run and target_run.priority == Priority.NORMAL.value:
                try:
                    new_lease = self.lease_manager.preempt_lease(
                        old_lease=lease,
                        new_run=emergency_run,
                    )

                    logger.warning(
                        f"抢占成功: emergency_run_id={emergency_run.id}, "
                        f"preempted_run_id={target_run.id}, "
                        f"device_id={lease.device_id}, "
                        f"new_lease_id={new_lease.id}"
                    )

                    return True

                except Exception as e:
                    logger.error(
                        f"抢占失败: lease_id={lease.id}, "
                        f"emergency_run_id={emergency_run.id}, error={e}"
                    )
                    continue

        logger.warning(
            f"抢占失败: 没有找到合适的抢占目标, "
            f"run_id={emergency_run.id}"
        )

        return False

    def get_scheduling_stats(self) -> dict:
        """获取调度统计信息.

        Returns:
            调度统计字典
        """
        # 统计各状态的任务数量
        queued_stmt = select(ScenarioRun).where(
            ScenarioRun.status == RunStatus.QUEUED.value
        )
        result = self.session.execute(queued_stmt)
        queued_count = len(list(result.scalars().all()))

        reserved_stmt = select(ScenarioRun).where(
            ScenarioRun.status == RunStatus.RESERVED.value
        )
        result = self.session.execute(reserved_stmt)
        reserved_count = len(list(result.scalars().all()))

        preempted_stmt = select(ScenarioRun).where(
            ScenarioRun.status == RunStatus.PREEMPTED.value
        )
        result = self.session.execute(preempted_stmt)
        preempted_count = len(list(result.scalars().all()))

        # 统计空闲设备数量
        idle_devices = self.pool_manager.get_candidate_devices()

        return {
            "queued_runs": queued_count,
            "reserved_runs": reserved_count,
            "preempted_runs": preempted_count,
            "idle_devices": len(idle_devices),
        }