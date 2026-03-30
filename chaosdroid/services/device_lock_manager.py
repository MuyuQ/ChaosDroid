"""设备锁管理模块.

提供设备锁定机制，防止同一设备上的并发执行。
支持锁超时和过期锁清理。
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class DeviceLock:
    """设备锁信息."""
    device_serial: str
    scenario_run_id: int
    acquired_at: datetime
    timeout_sec: int = 300  # 默认5分钟超时
    lock_holder: Optional[str] = None  # 锁持有者标识（可选）

    def is_expired(self) -> bool:
        """检查锁是否已过期."""
        expires_at = self.acquired_at + timedelta(seconds=self.timeout_sec)
        return datetime.utcnow() > expires_at

    def remaining_time(self) -> float:
        """获取锁剩余时间（秒）."""
        expires_at = self.acquired_at + timedelta(seconds=self.timeout_sec)
        remaining = (expires_at - datetime.utcnow()).total_seconds()
        return max(0.0, remaining)


class DeviceLockError(Exception):
    """设备锁定错误."""
    pass


class DeviceLockTimeoutError(DeviceLockError):
    """设备锁获取超时错误."""
    pass


class DeviceAlreadyLockedError(DeviceLockError):
    """设备已被锁定错误."""
    pass


class DeviceLockManager:
    """设备锁管理器.

    管理设备锁定状态，防止并发执行。
    支持锁超时和过期锁自动清理。

    Attributes:
        default_timeout: 默认锁超时时间（秒）
        cleanup_interval: 过期锁清理间隔（秒）
    """

    def __init__(
        self,
        default_timeout: int = 300,
        cleanup_interval: int = 60,
    ):
        """初始化设备锁管理器.

        Args:
            default_timeout: 默认锁超时时间（秒）
            cleanup_interval: 过期锁清理间隔（秒）
        """
        self._locks: Dict[str, DeviceLock] = {}
        self._lock_mutex = asyncio.Lock()
        self._default_timeout = default_timeout
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    async def start_cleanup_task(self) -> None:
        """启动过期锁清理任务."""
        if self._running:
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("设备锁清理任务已启动")

    async def stop_cleanup_task(self) -> None:
        """停止过期锁清理任务."""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        logger.info("设备锁清理任务已停止")

    async def _cleanup_loop(self) -> None:
        """过期锁清理循环."""
        while self._running:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self.cleanup_expired_locks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"清理过期锁时发生异常: {e}")

    async def cleanup_expired_locks(self) -> int:
        """清理所有过期锁.

        Returns:
            清理的过期锁数量
        """
        expired_count = 0
        async with self._lock_mutex:
            expired_devices = [
                serial for serial, lock in self._locks.items()
                if lock.is_expired()
            ]

            for serial in expired_devices:
                lock = self._locks.pop(serial)
                expired_count += 1
                logger.warning(
                    f"清理过期锁: device={serial}, "
                    f"run_id={lock.scenario_run_id}, "
                    f"acquired_at={lock.acquired_at.isoformat()}"
                )

        if expired_count > 0:
            logger.info(f"已清理 {expired_count} 个过期锁")

        return expired_count

    async def acquire_lock(
        self,
        device_serial: str,
        scenario_run_id: int,
        timeout_sec: Optional[int] = None,
        wait_timeout_sec: int = 30,
    ) -> DeviceLock:
        """获取设备锁.

        如果设备已被锁定，会等待直到锁释放或等待超时。

        Args:
            device_serial: 设备序列号
            scenario_run_id: 场景执行ID
            timeout_sec: 锁超时时间（秒），None使用默认值
            wait_timeout_sec: 等待锁释放的超时时间（秒）

        Returns:
            获取到的设备锁

        Raises:
            DeviceLockTimeoutError: 等待锁释放超时
            DeviceAlreadyLockedError: 设备已被锁定且无法等待
        """
        lock_timeout = timeout_sec or self._default_timeout
        wait_start = datetime.utcnow()

        while True:
            async with self._lock_mutex:
                # 检查是否存在锁
                existing_lock = self._locks.get(device_serial)

                if existing_lock is None:
                    # 设备未被锁定，直接获取锁
                    lock = DeviceLock(
                        device_serial=device_serial,
                        scenario_run_id=scenario_run_id,
                        acquired_at=datetime.utcnow(),
                        timeout_sec=lock_timeout,
                    )
                    self._locks[device_serial] = lock
                    logger.info(
                        f"获取设备锁成功: device={device_serial}, "
                        f"run_id={scenario_run_id}, "
                        f"timeout={lock_timeout}s"
                    )
                    return lock

                # 检查现有锁是否过期
                if existing_lock.is_expired():
                    # 清理过期锁并获取新锁
                    logger.warning(
                        f"发现过期锁: device={device_serial}, "
                        f"old_run_id={existing_lock.scenario_run_id}"
                    )
                    self._locks.pop(device_serial)

                    lock = DeviceLock(
                        device_serial=device_serial,
                        scenario_run_id=scenario_run_id,
                        acquired_at=datetime.utcnow(),
                        timeout_sec=lock_timeout,
                    )
                    self._locks[device_serial] = lock
                    logger.info(
                        f"获取设备锁成功（替换过期锁）: device={device_serial}, "
                        f"run_id={scenario_run_id}"
                    )
                    return lock

            # 设备被锁定且未过期，等待锁释放
            waited_time = (datetime.utcnow() - wait_start).total_seconds()
            if waited_time >= wait_timeout_sec:
                raise DeviceLockTimeoutError(
                    f"等待设备锁超时: device={device_serial}, "
                    f"waited={waited_time:.1f}s, "
                    f"locked_by_run_id={existing_lock.scenario_run_id}"
                )

            # 等待一小段时间后重试
            remaining_lock_time = existing_lock.remaining_time()
            wait_time = min(1.0, remaining_lock_time)
            logger.debug(
                f"等待设备锁释放: device={device_serial}, "
                f"locked_by={existing_lock.scenario_run_id}, "
                f"remaining={remaining_lock_time:.1f}s"
            )
            await asyncio.sleep(wait_time)

    async def release_lock(
        self,
        device_serial: str,
        scenario_run_id: int,
    ) -> bool:
        """释放设备锁.

        Args:
            device_serial: 设备序列号
            scenario_run_id: 场景执行ID（用于验证锁所有权）

        Returns:
            是否成功释放锁
        """
        async with self._lock_mutex:
            lock = self._locks.get(device_serial)

            if lock is None:
                logger.warning(
                    f"尝试释放不存在的锁: device={device_serial}"
                )
                return False

            if lock.scenario_run_id != scenario_run_id:
                logger.warning(
                    f"锁所有权不匹配，拒绝释放: "
                    f"device={device_serial}, "
                    f"expected_run_id={lock.scenario_run_id}, "
                    f"actual_run_id={scenario_run_id}"
                )
                return False

            self._locks.pop(device_serial)
            logger.info(
                f"释放设备锁成功: device={device_serial}, "
                f"run_id={scenario_run_id}"
            )
            return True

    async def force_release_lock(
        self,
        device_serial: str,
        reason: str = "force_release",
    ) -> bool:
        """强制释放设备锁（管理员操作）.

        Args:
            device_serial: 设备序列号
            reason: 强制释放原因

        Returns:
            是否成功释放锁
        """
        async with self._lock_mutex:
            lock = self._locks.get(device_serial)

            if lock is None:
                logger.debug(f"设备未被锁定: device={device_serial}")
                return False

            self._locks.pop(device_serial)
            logger.warning(
                f"强制释放设备锁: device={device_serial}, "
                f"run_id={lock.scenario_run_id}, "
                f"reason={reason}"
            )
            return True

    async def is_locked(self, device_serial: str) -> bool:
        """检查设备是否被锁定.

        Args:
            device_serial: 设备序列号

        Returns:
            设备是否被锁定
        """
        async with self._lock_mutex:
            lock = self._locks.get(device_serial)
            if lock is None:
                return False
            # 检查锁是否过期
            return not lock.is_expired()

    async def get_lock_info(self, device_serial: str) -> Optional[DeviceLock]:
        """获取设备锁信息.

        Args:
            device_serial: 设备序列号

        Returns:
            设备锁信息，如果未被锁定则返回None
        """
        async with self._lock_mutex:
            lock = self._locks.get(device_serial)
            if lock and lock.is_expired():
                return None
            return lock

    async def get_all_locks(self) -> Dict[str, DeviceLock]:
        """获取所有活跃锁信息.

        Returns:
            设备序列号到锁信息的映射
        """
        async with self._lock_mutex:
            # 过滤掉过期锁
            active_locks = {
                serial: lock
                for serial, lock in self._locks.items()
                if not lock.is_expired()
            }
            return active_locks

    async def get_locked_devices(self) -> Set[str]:
        """获取所有被锁定的设备序列号.

        Returns:
            被锁定的设备序列号集合
        """
        async with self._lock_mutex:
            return {
                serial
                for serial, lock in self._locks.items()
                if not lock.is_expired()
            }


# 全局设备锁管理器实例
_device_lock_manager: Optional[DeviceLockManager] = None


def get_device_lock_manager() -> DeviceLockManager:
    """获取设备锁管理器实例."""
    global _device_lock_manager
    if _device_lock_manager is None:
        _device_lock_manager = DeviceLockManager()
    return _device_lock_manager


async def init_device_lock_manager(
    default_timeout: int = 300,
    cleanup_interval: int = 60,
) -> DeviceLockManager:
    """初始化并启动设备锁管理器.

    Args:
        default_timeout: 默认锁超时时间（秒）
        cleanup_interval: 过期锁清理间隔（秒）

    Returns:
        设备锁管理器实例
    """
    global _device_lock_manager
    if _device_lock_manager is None:
        _device_lock_manager = DeviceLockManager(
            default_timeout=default_timeout,
            cleanup_interval=cleanup_interval,
        )
    await _device_lock_manager.start_cleanup_task()
    return _device_lock_manager


async def shutdown_device_lock_manager() -> None:
    """关闭设备锁管理器."""
    global _device_lock_manager
    if _device_lock_manager:
        await _device_lock_manager.stop_cleanup_task()
        _device_lock_manager = None