"""
数据库模型模块。

导出所有数据库模型、枚举和数据库工具。
"""

# 基类和枚举
from .base import (
    ArtifactType,
    Base,
    DevicePoolPurpose,
    DeviceStatus,
    EventSeverity,
    EventType,
    ExecutorMode,
    FaultType,
    InjectStage,
    LeaseStatus,
    Priority,
    RiskLevel,
    RunStatus,
    StepStatus,
    StepType,
    TargetType,
    TimestampMixin,
)

# 数据库管理
from .database import (
    close_engine,
    create_tables,
    drop_tables,
    get_database_url,
    get_engine,
    get_session,
    get_session_context,
    get_session_factory,
    init_engine,
)


# 初始化数据库的便捷函数
async def init_db(database_path: str = "chaosdroid.db") -> None:
    """初始化数据库引擎并创建表结构."""
    init_engine(database_path)
    await create_tables()


# 模型
from .artifact import Artifact, Report
from .device import Device
from .device_lease import DeviceLease
from .device_pool import DevicePool
from .event import IncidentEvent
from .event_queue import EventQueue
from .profiles import FaultProfile, RecoveryProfile, ValidationProfile
from .scenario import ScenarioRun, ScenarioStep, ScenarioTemplate

__all__ = [
    # 基类和混入
    "Base",
    "TimestampMixin",
    # 枚举
    "RunStatus",
    "StepType",
    "StepStatus",
    "FaultType",
    "InjectStage",
    "TargetType",
    "RiskLevel",
    "ExecutorMode",
    "ArtifactType",
    # 调度相关枚举（从 scheduling/enums.py 迁移而来）
    "DeviceStatus",
    "DevicePoolPurpose",
    "LeaseStatus",
    "Priority",
    "EventType",
    "EventSeverity",
    # 数据库管理
    "get_database_url",
    "init_engine",
    "init_db",
    "get_engine",
    "get_session_factory",
    "get_session",
    "get_session_context",
    "create_tables",
    "drop_tables",
    "close_engine",
    # 模型
    "FaultProfile",
    "ValidationProfile",
    "RecoveryProfile",
    "ScenarioTemplate",
    "ScenarioRun",
    "ScenarioStep",
    "Artifact",
    "Report",
    "Device",
    "DevicePool",
    "DeviceLease",
    "IncidentEvent",
    "EventQueue",
]