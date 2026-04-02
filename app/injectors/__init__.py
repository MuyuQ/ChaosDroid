"""注入器模块。

提供所有故障注入器的实现和注册机制。
"""

from .base import (
    BaseInjector,
    InjectContext,
    InjectResult,
    INJECTOR_REGISTRY,
    register_injector,
    get_injector,
    list_injectors,
)
from app.models.base import FaultType, RiskLevel

# 导入并注册所有注入器
from .storage_pressure import StoragePressureInjector
from .low_battery import LowBatteryInjector
from .network_jitter import NetworkJitterInjector
from .reboot_timeout import RebootTimeoutInjector
from .cpu_io_stress import CpuIoStressInjector
from .monkey_stability import MonkeyStabilityInjector

__all__ = [
    # 基类
    "BaseInjector",
    "FaultType",
    "RiskLevel",
    "InjectContext",
    "InjectResult",
    # 注册机制
    "INJECTOR_REGISTRY",
    "register_injector",
    "get_injector",
    "list_injectors",
    # 注入器实现
    "StoragePressureInjector",
    "LowBatteryInjector",
    "NetworkJitterInjector",
    "RebootTimeoutInjector",
    "CpuIoStressInjector",
    "MonkeyStabilityInjector",
]