"""
SQLAlchemy 2.0 数据库模型基础模块。

提供所有模型的基类和枚举定义。
"""

from datetime import datetime
from enum import Enum
from typing import AsyncGenerator

from sqlalchemy import JSON, DateTime, Integer, String, Boolean, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """所有数据库模型的基类。"""

    pass


class TimestampMixin:
    """时间戳混入类，提供 created_at 和 updated_at 字段。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        nullable=False,
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )


class RunStatus(str, Enum):
    """场景执行状态枚举。"""

    QUEUED = "queued"  # 排队中
    ALLOCATING = "allocating"  # 正在分配设备
    RESERVED = "reserved"  # 已分配设备，等待执行
    PREPARING = "preparing"  # 准备中
    INJECTING = "injecting"  # 注入中
    VALIDATING = "validating"  # 验证中
    RECOVERING = "recovering"  # 恢复中
    PASSED = "passed"  # 通过
    FAILED = "failed"  # 失败
    PARTIAL = "partial"  # 部分通过
    PREEMPTED = "preempted"  # 被抢占


class StepType(str, Enum):
    """执行步骤类型枚举。"""

    PRECHECK = "precheck"  # 前置检查
    INJECT = "inject"  # 故障注入
    OBSERVE = "observe"  # 观测采集
    VALIDATE = "validate"  # 验证判定
    RECOVER = "recover"  # 恢复操作
    COLLECT = "collect"  # 产物收集


class StepStatus(str, Enum):
    """执行步骤状态枚举。"""

    PENDING = "pending"  # 待执行
    RUNNING = "running"  # 执行中
    SUCCESS = "success"  # 成功
    FAILED = "failed"  # 失败
    SKIPPED = "skipped"  # 跳过
    TIMEOUT = "timeout"  # 超时


class FaultType(str, Enum):
    """故障类型枚举。"""

    storage_pressure = "storage_pressure"  # 存储压力
    low_battery = "low_battery"  # 低电量
    network_jitter = "network_jitter"  # 网络波动
    reboot_timeout = "reboot_timeout"  # 重启超时
    cpu_io_stress = "cpu_io_stress"  # CPU/I/O 压力
    monkey_stability = "monkey_stability"  # Monkey 稳定性


class InjectStage(str, Enum):
    """注入阶段枚举。"""

    PRECHECK = "precheck"  # 前置检查阶段
    PREPARE = "prepare"  # 准备阶段
    UPGRADING = "upgrading"  # 升级进行中
    REBOOT_WAIT = "reboot_wait"  # 重启等待
    POST_BOOT = "post_boot"  # 启动后
    POST_VALIDATE = "post_validate"  # 验证后


class TargetType(str, Enum):
    """目标类型枚举。"""

    UPGRADE = "upgrade"  # 升级链路测试
    STABILITY = "stability"  # 稳定性测试
    MONKEY = "monkey"  # Monkey 压测
    RECOVERY = "recovery"  # 恢复能力验证


class RiskLevel(str, Enum):
    """风险等级枚举。"""

    low = "low"  # 不影响关键链路
    medium = "medium"  # 影响升级链路
    high = "high"  # 影响 boot 或系统可用性
    critical = "critical"  # 需要人工介入恢复


class ExecutorMode(str, Enum):
    """执行器模式枚举。"""

    REAL = "real"  # 真实设备
    MOCK = "mock"  # 模拟设备


class ArtifactType(str, Enum):
    """产物类型枚举。"""

    LOGCAT = "logcat"  # logcat 日志
    GETPROP = "getprop"  # 属性摘要
    BATTERY = "battery"  # 电池信息
    MONKEY = "monkey"  # Monkey 输出
    STDOUT = "stdout"  # 标准输出
    STDERR = "stderr"  # 标准错误
    SNAPSHOT = "snapshot"  # 状态快照
    SUMMARY = "summary"  # 步骤摘要
    OTHER = "other"  # 其他


# =============================================================================
# 设备与调度相关枚举（从 scheduling/enums.py 迁移而来，保持向后兼容）
# =============================================================================


class DeviceStatus(str, Enum):
    """设备状态枚举。"""

    IDLE = "idle"  # 空闲
    RESERVED = "reserved"  # 已预留
    BUSY = "busy"  # 忙碌
    OFFLINE = "offline"  # 离线
    QUARANTINED = "quarantined"  # 已隔离
    RECOVERING = "recovering"  # 恢复中


class DevicePoolPurpose(str, Enum):
    """设备池用途枚举。"""

    STABLE = "stable"  # 稳定测试
    STRESS = "stress"  # 压力测试
    EMERGENCY = "emergency"  # 紧急任务


class LeaseStatus(str, Enum):
    """设备租约状态枚举。"""

    ACTIVE = "active"  # 活跃
    RELEASED = "released"  # 已释放
    PREEMPTED = "preempted"  # 被抢占
    EXPIRED = "expired"  # 已过期


class Priority(str, Enum):
    """任务优先级枚举。"""

    NORMAL = "normal"  # 普通
    HIGH = "high"  # 高
    EMERGENCY = "emergency"  # 紧急


class EventType(str, Enum):
    """事件类型枚举。"""

    DEVICE_OFFLINE = "device_offline"  # 设备离线
    HEALTH_FAILED = "health_failed"  # 健康检查失败
    LEASE_CREATED = "lease_created"  # 租约创建
    PREEMPTION_TRIGGERED = "preemption_triggered"  # 抢占触发
    DEVICE_QUARANTINED = "device_quarantined"  # 设备被隔离
    DEVICE_RECOVERED = "device_recovered"  # 设备恢复
    DEVICE_RECOVERY_FAILED = "device_recovery_failed"  # 设备恢复失败


class EventSeverity(str, Enum):
    """事件严重程度枚举。"""

    INFO = "info"  # 信息
    WARNING = "warning"  # 警告
    ERROR = "error"  # 错误
    CRITICAL = "critical"  # 严重
