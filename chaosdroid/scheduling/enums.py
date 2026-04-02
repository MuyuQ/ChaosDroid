"""Scheduling-related enumerations.

此模块已废弃，所有枚举已迁移到 chaosdroid.models.base。
为了保持向后兼容，此处重新导出 base.py 中的枚举定义。
"""

# 从 base.py 导入所有枚举，保持向后兼容
from chaosdroid.models.base import (
    DeviceStatus,
    DevicePoolPurpose,
    LeaseStatus,
    Priority,
    EventType,
    EventSeverity,
)

__all__ = [
    "DeviceStatus",
    "DevicePoolPurpose",
    "LeaseStatus",
    "Priority",
    "EventType",
    "EventSeverity",
]
