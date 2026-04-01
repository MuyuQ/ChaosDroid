"""Scheduling-related enumerations."""
from enum import Enum


class DeviceStatus(str, Enum):
    """设备状态."""
    IDLE = "idle"
    RESERVED = "reserved"
    BUSY = "busy"
    OFFLINE = "offline"
    QUARANTINED = "quarantined"
    RECOVERING = "recovering"


class DevicePoolPurpose(str, Enum):
    """设备池用途."""
    STABLE = "stable"
    STRESS = "stress"
    EMERGENCY = "emergency"


class LeaseStatus(str, Enum):
    """设备租约状态."""
    ACTIVE = "active"
    RELEASED = "released"
    PREEMPTED = "preempted"
    EXPIRED = "expired"


class Priority(str, Enum):
    """任务优先级."""
    NORMAL = "normal"
    HIGH = "high"
    EMERGENCY = "emergency"


class EventType(str, Enum):
    """事件类型."""
    DEVICE_OFFLINE = "device_offline"
    HEALTH_FAILED = "health_failed"
    LEASE_CREATED = "lease_created"
    PREEMPTION_TRIGGERED = "preemption_triggered"
    DEVICE_QUARANTINED = "device_quarantined"
    DEVICE_RECOVERED = "device_recovered"
    DEVICE_RECOVERY_FAILED = "device_recovery_failed"


class EventSeverity(str, Enum):
    """事件严重程度."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"