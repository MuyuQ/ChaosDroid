"""设备执行器基类."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List


class ExecutorMode(str, Enum):
    """执行模式枚举"""
    real = "real"
    mock = "mock"


class MockScenario(str, Enum):
    """Mock场景枚举"""
    normal = "normal"
    offline = "offline"
    low_battery = "low_battery"
    storage_full = "storage_full"
    boot_timeout = "boot_timeout"
    network_error = "network_error"


@dataclass
class StorageInfo:
    """存储信息"""
    total: int
    available: int
    used: int
    path: str = "/"


@dataclass
class BatteryInfo:
    """电池信息"""
    level: int
    status: str  # charging, discharging, full, unknown
    temperature: Optional[int] = None
    health: Optional[str] = None


@dataclass
class ShellResult:
    """Shell命令执行结果"""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int = 0


@dataclass
class MonkeyResult:
    """Monkey执行结果"""
    success: bool
    total_events: int
    crash_count: int
    anr_count: int
    output: str
    duration_ms: int = 0


class BaseDeviceExecutor(ABC):
    """设备执行器基类"""

    mode: ExecutorMode
    device_serial: str

    @abstractmethod
    async def is_online(self) -> bool:
        """检查设备是否在线"""
        pass

    @abstractmethod
    async def get_properties(self) -> Dict[str, str]:
        """
        获取设备属性

        Returns:
            Dict with key properties: model, android_version, brand, etc.
        """
        pass

    @abstractmethod
    async def get_storage_info(self) -> StorageInfo:
        """获取存储信息"""
        pass

    @abstractmethod
    async def get_battery_info(self) -> BatteryInfo:
        """获取电池信息"""
        pass

    @abstractmethod
    async def execute_shell(self, cmd: str, timeout: int = 30) -> ShellResult:
        """
        执行Shell命令

        Args:
            cmd: Command to execute
            timeout: Timeout in seconds

        Returns:
            ShellResult with output and status
        """
        pass

    @abstractmethod
    async def push_file(self, local_path: str, remote_path: str) -> bool:
        """
        推送文件到设备

        Args:
            local_path: Local file path
            remote_path: Remote path on device

        Returns:
            True if succeeded
        """
        pass

    @abstractmethod
    async def pull_file(self, remote_path: str, local_path: str) -> bool:
        """
        从设备拉取文件

        Args:
            remote_path: Remote path on device
            local_path: Local file path

        Returns:
            True if succeeded
        """
        pass

    @abstractmethod
    async def run_monkey(self, package: str, count: int, options: Dict[str, Any] = None) -> MonkeyResult:
        """
        运行Monkey测试

        Args:
            package: Package name
            count: Event count
            options: Monkey options

        Returns:
            MonkeyResult with test statistics
        """
        pass

    @abstractmethod
    async def reboot(self, wait_timeout: int = 120) -> bool:
        """
        重启设备并等待

        Args:
            wait_timeout: Wait timeout in seconds

        Returns:
            True if reboot succeeded and device came back online
        """
        pass

    async def wait_for_boot(self, timeout: int = 60) -> bool:
        """等待设备启动完成"""
        pass

    async def check_boot_completed(self) -> bool:
        """检查boot是否完成"""
        pass

    async def get_logcat(self, lines: int = 1000) -> str:
        """获取logcat日志"""
        pass