"""设备执行器模块。

提供真实设备和模拟设备的统一执行接口。
"""

from .base import (
    BaseDeviceExecutor,
    ExecutorMode,
    MockScenario,
    StorageInfo,
    BatteryInfo,
    ShellResult,
    MonkeyResult,
)
from .mock_executor import MockDeviceExecutor, MockDeviceState
from .real_executor import RealDeviceExecutor

__all__ = [
    # 基类
    "BaseDeviceExecutor",
    "ExecutorMode",
    "MockScenario",
    # 数据类
    "StorageInfo",
    "BatteryInfo",
    "ShellResult",
    "MonkeyResult",
    # 执行器实现
    "MockDeviceExecutor",
    "MockDeviceState",
    "RealDeviceExecutor",
]