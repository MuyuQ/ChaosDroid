# ChaosDroid + LabSentinel 整合设计文档

## 1. 项目概述

### 1.1 整合目标

将 LabSentinel 的设备池管理、任务调度、设备锁管理能力作为基础设施层引入 ChaosDroid，使 ChaosDroid 成为一个具备批量并发执行能力的故障注入测试平台。

### 1.2 整合原则

- **ChaosDroid 主导**：保持故障注入测试平台的核心定位，命名沿用 Scenario/Run
- **调度作为基础设施**：调度能力支撑故障注入，而非替代原有执行编排
- **深度合并**：代码完全融合，统一目录结构
- **最小改动**：尽量保留 ChaosDroid 原有模块的接口和行为

### 1.3 整合范围

| 来自 LabSentinel | 整合方式 |
|------------------|----------|
| DevicePool | 新增模型，设备池管理 |
| DeviceLease | 新增模型，设备租约管理 |
| Device（增强版） | 替换 ChaosDroid 的简单设备概念 |
| SchedulerService | 改造为 scheduling/scheduler.py |
| DeviceSyncService | 改造为 scheduling/device_sync.py |
| RecoveryService | 改造为 scheduling/quarantine.py |
| 演练引擎 | **不引入**（ChaosDroid 已有场景机制） |

---

## 2. 整体架构

整合后采用三层架构：

```
┌─────────────────────────────────────────────────────────────────┐
│                        表现层 (Presentation)                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   API Routes    │  │   CLI Commands  │  │   Web Pages     │  │
│  │  (FastAPI)      │  │    (Typer)      │  │   (Jinja2)      │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        业务层 (Business)                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   Orchestrators                          │    │
│  │  ExecutionOrchestrator: 准备→注入→验证→恢复→收集        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────┐│
│  │  Injectors  │  │ Validators  │  │  Observers  │  │ Reports ││
│  │  (6种故障)  │  │  (状态验证) │  │  (数据采集) │  │(MD/HTML)││
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      基础设施层 (Infrastructure)                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                     Scheduling                           │    │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌────────┐│    │
│  │  │Scheduler  │  │PoolManager│  │LeaseMgr   │  │Quarant ││    │
│  │  │(任务调度) │  │(设备池)   │  │(租约管理) │  │(隔离)  ││    │
│  │  └───────────┘  └───────────┘  └───────────┘  └────────┘│    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                     Device                               │    │
│  │  DeviceSyncService: 设备发现、状态同步、健康评分        │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                     Storage                              │    │
│  │  Models (SQLAlchemy) + Services + Config + Executors    │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 目录结构

整合后的目录结构：

```
chaosdroid/
├── scheduling/              # 新增：调度基础设施层
│   ├── __init__.py
│   ├── scheduler.py         # 任务调度器
│   ├── pool_manager.py      # 设备池管理
│   ├── lease_manager.py     # 设备租约管理
│   ├── device_sync.py       # 设备状态同步
│   ├── quarantine.py        # 设备隔离/恢复
│   └── enums.py             # 调度相关枚举
│
├── injectors/               # 保留：故障注入层
│   ├── __init__.py
│   ├── base.py
│   ├── storage_pressure.py
│   ├── low_battery.py
│   ├── network_jitter.py
│   ├── reboot_timeout.py
│   ├── cpu_io_stress.py
│   └── monkey_stability.py
│
├── orchestrators/           # 扩展：编排层
│   ├── __init__.py
│   ├── execution.py         # 执行编排（集成调度触发）
│   └── state_machine.py     # 状态机
│
├── validators/              # 保留：验证层
│   ├── __init__.py
│   └── base.py
│
├── observers/               # 保留：观测采集层
│   ├── __init__.py
│   └── collector.py
│
├── services/                # 合并：业务服务层
│   ├── __init__.py
│   ├── scenario_service.py  # 场景管理
│   ├── run_service.py       # 执行管理（扩展调度集成）
│   ├── profile_service.py   # 配置管理
│   ├── execution_service.py # 执行服务
│   ├── artifact_service.py  # 产物管理
│   ├── report_service.py    # 报告服务
│   ├── report_generator.py  # 报告生成
│   └── device_lock_manager.py  # 设备锁（保留，与 LeaseManager 协作）
│
├── models/                  # 扩展：统一数据模型
│   ├── __init__.py
│   ├── base.py              # 基础枚举（扩展调度枚举）
│   ├── scenario.py          # ScenarioTemplate/ScenarioRun（扩展调度字段）
│   ├── profiles.py          # FaultProfile/ValidationProfile/RecoveryProfile
│   ├── device.py            # Device（来自 LabSentinel，增强版）
│   ├── device_pool.py       # DevicePool（来自 LabSentinel）
│   ├── device_lease.py      # DeviceLease（来自 LabSentinel）
│   ├── event.py             # IncidentEvent（来自 LabSentinel）
│   ├── artifact.py          # Artifact
│   └── database.py          # 数据库配置
│
├── api/                     # 合并：API 层
│   ├── __init__.py
│   ├── main.py              # FastAPI 应用入口
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── scenarios.py     # 场景 API
│   │   ├── runs.py          # 执行 API（扩展调度操作）
│   │   ├── profiles.py      # 配置 API
│   │   ├── devices.py       # 设备 API（扩展池管理）
│   │   ├── pools.py         # 设备池 API（新增）
│   │   ├── reports.py       # 报告 API
│   │   └── web.py           # Web 页面
│   └── templates/           # Jinja2 模板
│
├── cli/                     # 合并：CLI 层
│   ├── __init__.py
│   ├── main.py              # CLI 入口
│   ├── init.py              # 初始化命令
│   ├── scenario.py          # 场景命令
│   ├── run.py               # 执行命令（扩展调度操作）
│   ├── device.py            # 设备命令（扩展池管理）
│   ├── pool.py              # 设备池命令（新增）
│   ├── report.py            # 报告命令
│   └── serve.py             # 服务命令
│
├── executors/               # 保留：执行器
│   ├── __init__.py
│   ├── base.py
│   ├── real_executor.py
│   └── mock_executor.py
│
├── config/                  # 保留：配置管理
│   ├── __init__.py
│   ├── settings.py
│   └── logging.py
│
├── templates/               # 保留：报告模板
│   └── reports/
│
├── tests/                   # 扩展：测试
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_injectors.py
│   ├── test_validators.py
│   ├── test_executors.py
│   ├── test_orchestrators.py
│   ├── test_services.py
│   ├── test_scheduling.py   # 新增
│   └── test_integration.py
│
└── main.py                  # 应用入口
```

---

## 4. 数据模型设计

### 4.1 枚举整合

整合两个项目的枚举，统一在 `models/base.py`：

```python
# 保留 ChaosDroid 原有枚举
class RunStatus(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    INJECTING = "injecting"
    VALIDATING = "validating"
    RECOVERING = "recovering"
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    # 新增：调度相关状态
    ALLOCATING = "allocating"      # 正在分配设备
    RESERVED = "reserved"          # 已分配设备，等待执行
    PREEMPTED = "preempted"        # 被抢占

class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"

class FaultType(str, Enum):
    storage_pressure = "storage_pressure"
    low_battery = "low_battery"
    network_jitter = "network_jitter"
    reboot_timeout = "reboot_timeout"
    cpu_io_stress = "cpu_io_stress"
    monkey_stability = "monkey_stability"

class InjectStage(str, Enum):
    PRECHECK = "precheck"
    PREPARE = "prepare"
    UPGRADING = "upgrading"
    REBOOT_WAIT = "reboot_wait"
    POST_BOOT = "post_boot"
    POST_VALIDATE = "post_validate"

class TargetType(str, Enum):
    UPGRADE = "upgrade"
    STABILITY = "stability"
    MONKEY = "monkey"
    RECOVERY = "recovery"

class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"

class ExecutorMode(str, Enum):
    REAL = "real"
    MOCK = "mock"

# 来自 LabSentinel，新增枚举
class DeviceStatus(str, Enum):
    IDLE = "idle"
    RESERVED = "reserved"
    BUSY = "busy"
    OFFLINE = "offline"
    QUARANTINED = "quarantined"
    RECOVERING = "recovering"

class DevicePoolPurpose(str, Enum):
    STABLE = "stable"
    STRESS = "stress"
    EMERGENCY = "emergency"

class LeaseStatus(str, Enum):
    ACTIVE = "active"
    RELEASED = "released"
    PREEMPTED = "preempted"
    EXPIRED = "expired"

class Priority(str, Enum):
    NORMAL = "normal"
    HIGH = "high"
    EMERGENCY = "emergency"

class EventType(str, Enum):
    DEVICE_OFFLINE = "device_offline"
    HEALTH_FAILED = "health_failed"
    LEASE_CREATED = "lease_created"
    PREEMPTION_TRIGGERED = "preemption_triggered"
    DEVICE_QUARANTINED = "device_quarantined"
    DEVICE_RECOVERED = "device_recovered"
    DEVICE_RECOVERY_FAILED = "device_recovery_failed"

class EventSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
```

### 4.2 ScenarioTemplate 扩展

在原有 ScenarioTemplate 模型基础上，新增调度相关字段：

```python
class ScenarioTemplate(Base, TimestampMixin):
    __tablename__ = "scenario_templates"

    # 原有字段保留
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    target_type: Mapped[str] = mapped_column(String(50), default="stability")
    fault_profile_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("fault_profiles.id"))
    inject_stage: Mapped[str] = mapped_column(String(50), default="precheck")
    validation_profile_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("validation_profiles.id"))
    recovery_profile_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("recovery_profiles.id"))
    executor_mode: Mapped[str] = mapped_column(String(20), default="mock")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # 新增：调度相关字段
    default_priority: Mapped[str] = mapped_column(
        String(16),
        default=Priority.NORMAL.value,
        comment="默认优先级: normal/high/emergency"
    )
    device_pool_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("device_pools.id"),
        comment="默认设备池ID"
    )
    device_selector_json: Mapped[dict | None] = mapped_column(
        JSON,
        comment="设备选择条件，如 {'tags': ['stable'], 'min_health': 60}"
    )
    interruptible: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="是否可被 emergency 任务抢占"
    )
    max_concurrent: Mapped[int | None] = mapped_column(
        Integer,
        default=1,
        comment="最大并发执行数"
    )

    # 关系
    fault_profile: Mapped["FaultProfile | None"] = relationship(...)
    validation_profile: Mapped["ValidationProfile | None"] = relationship(...)
    recovery_profile: Mapped["RecoveryProfile | None"] = relationship(...)
    device_pool: Mapped["DevicePool | None"] = relationship(...)  # 新增
    runs: Mapped[list["ScenarioRun"]] = relationship(...)
```

### 4.3.1 状态流转

整合后的 ScenarioRun 状态流转：

```
                    ┌──────────────────────────────────────────────────┐
                    │                                                  │
                    ▼                                                  │
              ┌──────────┐     ┌───────────┐     ┌───────────┐        │
              │  QUEUED  │────►│ ALLOCATING│────►│  RESERVED │        │
              └──────────┘     └───────────┘     └───────────┘        │
                    │                                    │             │
                    │ 无可用设备                          │ 分配成功    │
                    │ 保持 QUEUED                        ▼             │
                    │                          ┌───────────┐          │
                    │                          │ PREPARING │          │
                    │                          └───────────┘          │
                    │                                │                 │
                    │                                ▼                 │
                    │                          ┌───────────┐          │
                    │                          │ INJECTING │          │
                    │                          └───────────┘          │
                    │                                │                 │
                    │                                ▼                 │
                    │                          ┌───────────┐          │
                    │                          │ VALIDATING│          │
                    │                          └───────────┘          │
                    │                                │                 │
                    │                                ▼                 │
                    │                          ┌───────────┐          │
                    │                          │ RECOVERING│          │
                    │                          └───────────┘          │
                    │                                │                 │
                    │                ┌───────────────┼───────────────┐│
                    │                ▼               ▼               ▼│
                    │          ┌─────────┐     ┌─────────┐     ┌────────┐
                    │          │ PASSED  │     │ FAILED  │     │PARTIAL │
                    │          └─────────┘     └─────────┘     └────────┘
                    │
                    │ emergency 抢占
                    ▼
              ┌───────────┐
              │ PREEMPTED │
              └───────────┘
```

### 4.3.2 device_serial 与 device_id 关系

ScenarioRun 同时保留 `device_serial` 和 `device_id` 字段：

- **device_serial**：用户指定的设备序列号，可为 `"auto"` 表示自动分配。保留用于：
  - 兼容原有 API（直接指定设备执行）
  - 记录用户原始意图
  - 执行日志中的设备标识

- **device_id**：调度器实际分配的设备 ID，外键关联 Device 表。仅在调度成功后填充。

**字段填充规则：**

| 场景 | device_serial | device_id |
|------|---------------|-----------|
| 用户指定具体设备 | 用户指定的序列号 | 调度时匹配 Device.id |
| 用户指定 `--device auto` | `"auto"` | 调度时分配的 Device.id |
| 通过 ScenarioTemplate 提交 | `"auto"` | 调度时分配的 Device.id |

### 4.3 ScenarioRun 扩展

在原有 ScenarioRun 模型基础上，新增调度和设备关联字段：

```python
class ScenarioRun(Base, TimestampMixin):
    __tablename__ = "scenario_runs"

    # 原有字段保留
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scenario_template_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("scenario_templates.id"))
    device_serial: Mapped[str] = mapped_column(String(100), nullable=False)  # 保留，兼容性
    status: Mapped[str] = mapped_column(String(20), default=RunStatus.QUEUED.value)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    inject_stage: Mapped[str] = mapped_column(String(50), default="precheck")
    result_summary_json: Mapped[str | None] = mapped_column(Text)

    # 新增：调度相关字段
    priority: Mapped[str] = mapped_column(
        String(16),
        default=Priority.NORMAL.value,
        index=True,
        comment="执行优先级"
    )
    device_pool_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("device_pools.id"),
        comment="执行设备池"
    )
    device_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("devices.id"),
        comment="实际分配的设备ID"
    )
    lease_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("device_leases.id"),
        comment="设备租约ID"
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        index=True,
        comment="提交时间"
    )
    allocated_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        comment="设备分配时间"
    )
    preempted_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        comment="被抢占时间（如有）"
    )
    preempted_by_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("scenario_runs.id"),
        comment="抢占此任务的任务ID"
    )
    interruptible: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="是否可被抢占"
    )

    # 关系
    scenario_template: Mapped["ScenarioTemplate | None"] = relationship(...)
    steps: Mapped[list["ScenarioStep"]] = relationship(...)
    artifacts: Mapped[list["Artifact"]] = relationship(...)
    report: Mapped["Report | None"] = relationship(...)
    device: Mapped["Device | None"] = relationship(...)        # 新增
    device_pool: Mapped["DevicePool | None"] = relationship(...)  # 新增
    lease: Mapped["DeviceLease | None"] = relationship(...)    # 新增
    preempted_by: Mapped["ScenarioRun | None"] = relationship(...)  # 新增

    # 索引
    __table_args__ = (
        Index("ix_scenario_runs_status_priority_submitted", "status", "priority", "submitted_at"),
        Index("ix_scenario_runs_device_id", "device_id"),
    )
```

### 4.4 Device 模型（来自 LabSentinel）

```python
class Device(Base, TimestampMixin):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    serial: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    model: Mapped[str | None] = mapped_column(String(128))
    brand: Mapped[str | None] = mapped_column(String(64))
    android_version: Mapped[str | None] = mapped_column(String(32))
    build_fingerprint: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), default=DeviceStatus.IDLE.value, index=True)
    health_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    battery_level: Mapped[int | None] = mapped_column(Integer)
    pool_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("device_pools.id"))
    tags_json: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    quarantine_reason: Mapped[str | None] = mapped_column(Text)
    executor_mode: Mapped[str] = mapped_column(String(8), default="mock")
    sync_failure_count: Mapped[int] = mapped_column(Integer, default=0)

    # 关系
    pool: Mapped["DevicePool | None"] = relationship(...)
    leases: Mapped[list["DeviceLease"]] = relationship(...)
    runs: Mapped[list["ScenarioRun"]] = relationship(...)  # 新增关联
    events: Mapped[list["IncidentEvent"]] = relationship(...)

    __table_args__ = (
        Index('ix_devices_status_health', 'status', 'health_score'),
    )
```

### 4.5 DevicePool 模型

```python
class DevicePool(Base, TimestampMixin):
    __tablename__ = "device_pools"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    reserved_emergency_ratio: Mapped[float] = mapped_column(Float, default=0.2)
    max_parallel_jobs: Mapped[int | None] = mapped_column(Integer)
    tag_selector_json: Mapped[dict | None] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # 关系
    devices: Mapped[list["Device"]] = relationship(...)
    scenario_templates: Mapped[list["ScenarioTemplate"]] = relationship(...)
    runs: Mapped[list["ScenarioRun"]] = relationship(...)
```

### 4.6 DeviceLease 模型

```python
class DeviceLease(Base, TimestampMixin):
    __tablename__ = "device_leases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    scenario_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("scenario_runs.id"),
        index=True,
        comment="关联的场景执行ID"
    )
    lease_status: Mapped[str] = mapped_column(String(16), default=LeaseStatus.ACTIVE.value, index=True)
    leased_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    released_at: Mapped[datetime | None] = mapped_column(DateTime)
    preemptible: Mapped[bool] = mapped_column(Boolean, default=False)

    # 关系
    device: Mapped["Device"] = relationship(...)
    scenario_run: Mapped["ScenarioRun | None"] = relationship(...)
```

### 4.7 IncidentEvent 模型

```python
class IncidentEvent(Base, TimestampMixin):
    __tablename__ = "incident_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("devices.id"), index=True)
    scenario_run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("scenario_runs.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), default=EventSeverity.INFO.value)
    payload_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # 关系
    device: Mapped["Device | None"] = relationship(...)
    scenario_run: Mapped["ScenarioRun | None"] = relationship(...)
```

---

## 5. 调度层模块设计

### 5.1 Scheduler（调度器）

位置：`scheduling/scheduler.py`

职责：
- 从数据库读取 queued 状态的 ScenarioRun
- 按 priority 和 submitted_at 排序
- 为任务分配设备（创建 DeviceLease）
- 处理 emergency 任务的抢占逻辑
- 调用 Orchestrator 触发执行

核心接口：

```python
class Scheduler:
    """任务调度器"""

    def __init__(self, session: Session, orchestrator: ExecutionOrchestrator):
        self.session = session
        self.orchestrator = orchestrator
        self.pool_manager = PoolManager(session)
        self.lease_manager = LeaseManager(session)

    def schedule_once(self) -> int:
        """执行一次调度循环，返回成功分配的任务数"""
        # 1. 查询 queued 状态的任务
        # 2. 按优先级排序
        # 3. 尝试分配设备
        # 4. 分配成功后调用 orchestrator.execute(run_id)
        # 5. 处理抢占逻辑（emergency 任务）

    def _try_allocate(self, run: ScenarioRun) -> bool:
        """尝试为任务分配设备"""

    def _try_preempt(self, emergency_run: ScenarioRun) -> bool:
        """尝试抢占任务"""
```

### 5.2 PoolManager（设备池管理）

位置：`scheduling/pool_manager.py`

职责：
- 获取设备池可用容量
- 查询候选设备列表
- 设备池 CRUD 操作

核心接口：

```python
class PoolManager:
    """设备池管理"""

    def __init__(self, session: Session):
        self.session = session

    def get_available_capacity(self, pool: DevicePool) -> int:
        """获取设备池可用容量"""

    def get_candidate_devices(
        self,
        pool_id: int | None = None,
        min_health: int = 40,
        required_tags: list[str] | None = None
    ) -> list[Device]:
        """获取候选设备列表"""

    def select_best_device(self, candidates: list[Device]) -> Device | None:
        """从候选设备中选择最佳设备（按健康分、空闲时长排序）"""

    def create_pool(self, name: str, purpose: str, **kwargs) -> DevicePool:
        """创建设备池"""

    def get_pool(self, pool_id: int) -> DevicePool | None:
        """获取设备池"""
```

### 5.3 LeaseManager（租约管理）

位置：`scheduling/lease_manager.py`

职责：
- 创建/释放设备租约
- 租约状态管理
- 租约查询

核心接口：

```python
class LeaseManager:
    """设备租约管理"""

    def __init__(self, session: Session):
        self.session = session

    def create_lease(self, device: Device, run: ScenarioRun) -> DeviceLease:
        """创建设备租约"""

    def release_lease(self, lease: DeviceLease) -> bool:
        """释放设备租约"""

    def preempt_lease(self, lease: DeviceLease, new_run: ScenarioRun) -> DeviceLease:
        """抢占租约"""

    def get_active_lease(self, device_id: int) -> DeviceLease | None:
        """获取设备的活跃租约"""

    def get_run_lease(self, run_id: int) -> DeviceLease | None:
        """获取任务的租约"""
```

### 5.4 DeviceSyncService（设备同步）

位置：`scheduling/device_sync.py`

职责：
- 发现设备（通过 ADB 或 Mock）
- 同步设备状态和属性
- 计算健康评分
- 触发隔离逻辑

核心接口：

```python
class DeviceSyncService:
    """设备状态同步"""

    def __init__(self, session: Session, executor_mode: ExecutorMode):
        self.session = session
        self.executor_mode = executor_mode

    async def sync_all(self) -> int:
        """同步所有设备状态"""

    async def sync_device(self, serial: str) -> Device:
        """同步单个设备"""

    def calculate_health_score(self, device: Device) -> int:
        """计算设备健康评分"""
        # 规则：
        # - 在线: +40
        # - boot_completed: +20
        # - 电量 > 30%: +20
        # - 最近无错误: +10
        # - 不在隔离状态: +10

    async def check_and_quarantine(self) -> int:
        """检查并隔离异常设备"""
```

### 5.5 QuarantineService（隔离恢复）

位置：`scheduling/quarantine.py`

职责：
- 设备隔离逻辑
- 设备恢复流程
- 隔离事件记录

核心接口：

```python
class QuarantineService:
    """设备隔离与恢复"""

    def __init__(self, session: Session):
        self.session = session

    def quarantine_device(
        self,
        device: Device,
        reason: str,
        severity: EventSeverity = EventSeverity.WARNING
    ) -> bool:
        """隔离设备"""

    async def recover_device(self, device: Device) -> bool:
        """恢复设备"""
        # 步骤：
        # 1. 基础连通性检查
        # 2. 属性读取检查
        # 3. 电量与 boot 状态检查
        # 4. 通过后改回 IDLE 状态

    def get_quarantined_devices(self) -> list[Device]:
        """获取隔离设备列表"""
```

---

## 6. 编排层集成设计

### 6.1 ExecutionOrchestrator 扩展

扩展原有 `orchestrators/execution.py` 的 `ScenarioExecution` 类，集成调度触发：

```python
class ScenarioExecution:
    """场景执行编排"""

    def __init__(self, scenario_run_id: int, session: Session):
        self.scenario_run_id = scenario_run_id
        self.session = session
        self.lease_manager = LeaseManager(session)
        # ... 其他初始化

    async def execute_with_lease(self) -> Dict[str, Any]:
        """在有租约的情况下执行"""
        # 获取租约和设备
        lease = self.lease_manager.get_run_lease(self.scenario_run_id)
        if not lease:
            raise ValueError("没有活跃的设备租约")

        device = lease.device

        # 创建执行器
        executor = self._create_executor(device)

        # 执行完整流程
        result = await self.run_full_execution(executor, ...)

        # 执行完成后释放租约
        self.lease_manager.release_lease(lease)

        # 更新设备状态
        device.status = DeviceStatus.IDLE

        return result

    async def on_preemption(self) -> bool:
        """被抢占时的清理逻辑"""
        # 1. 停止当前执行
        # 2. 清理注入效果（如已注入）
        # 3. 释放租约
        # 4. 更新状态为 PREEMPTED
```

### 6.2 Scheduler 与 Orchestrator 的交互

```python
# 在 Scheduler._try_allocate 成功后
def _allocate_device(self, device: Device, run: ScenarioRun) -> bool:
    # 创建租约
    lease = self.lease_manager.create_lease(device, run)

    # 更新状态
    run.status = RunStatus.RESERVED.value
    run.allocated_at = datetime.now(timezone.utc)

    # 触发执行（异步）
    asyncio.create_task(self.orchestrator.execute_with_lease(run.id))

    return True
```

---

## 7. 执行流程设计

### 7.0 Worker 模式设计

整合后支持两种运行模式：

#### 7.0.1 同步执行模式（原有）

```bash
# 用户通过 CLI 或 API 直接触发执行
chaosdroid run execute 1 --device ABC123
```

流程：
1. 用户提交执行请求
2. 立即尝试获取设备锁
3. 同步执行故障注入流程
4. 返回执行结果

适用于：单设备调试、快速验证场景。

#### 7.0.2 异步调度模式（新增）

```bash
# 启动后台 Worker
chaosdroid worker run --interval 5

# 用户提交任务到队列
chaosdroid run submit 1 --priority high --pool stable
```

Worker 架构：

```python
class Worker:
    """后台工作进程"""

    def __init__(self, session: Session, interval: int = 5):
        self.session = session
        self.interval = interval
        self.scheduler = Scheduler(session)
        self.sync_service = DeviceSyncService(session)

    async def run(self):
        """主循环"""
        while True:
            try:
                # 1. 同步设备状态
                await self.sync_service.sync_all()

                # 2. 执行调度
                self.scheduler.schedule_once()

                # 3. 检查隔离设备
                await self.sync_service.check_and_quarantine()

            except Exception as e:
                logger.error(f"Worker 循环异常: {e}")

            await asyncio.sleep(self.interval)
```

适用于：批量执行、生产环境、需要抢占调度的场景。

### 7.0.3 DeviceLockManager 与 LeaseManager 协作

原有的 `DeviceLockManager`（内存锁）与新增的 `LeaseManager`（数据库租约）协作：

| 机制 | 作用范围 | 用途 |
|------|----------|------|
| DeviceLockManager | 进程内存 | 同步执行模式下防止同一进程内并发冲突 |
| LeaseManager | 数据库 | 异步调度模式下实现跨进程的设备租约 |

**协作逻辑：**

```python
class ScenarioExecution:
    async def execute_with_lease(self):
        # 1. 获取数据库租约（LeaseManager）
        lease = self.lease_manager.get_run_lease(self.scenario_run_id)

        # 2. 获取内存锁（DeviceLockManager）- 防止同一进程内冲突
        async with self.device_lock_manager.acquire(lease.device.serial):
            try:
                # 3. 执行故障注入
                result = await self.run_full_execution(...)

            except PreemptionException:
                # 被抢占时确保租约被正确处理
                await self.on_preemption()
                raise

            finally:
                # 4. 释放内存锁
                pass  # 通过 async with 自动释放

        # 5. 释放数据库租约
        self.lease_manager.release_lease(lease)
```

### 7.1 完整执行流程

```
用户提交 Scenario
    │
    ▼
创建 ScenarioRun (status=queued)
    │
    ▼
Scheduler 调度循环
    │
    ├─ 查询 queued 任务
    │
    ├─ 按优先级排序
    │
    ├─ 尝试分配设备
    │   │
    │   ├─ 有空闲设备 → 创建租约 → 状态改为 reserved
    │   │
    │   ├─ 无空闲设备 + emergency → 尝试抢占
    │   │
    │   └─ 无空闲设备 + normal → 保持 queued
    │
    ▼
Orchestrator 执行（状态变为 preparing → injecting → validating → recovering）
    │
    ├─ 准备阶段：检查设备状态、采集初始信息
    │
    ├─ 注入阶段：执行故障注入
    │
    ├─ 验证阶段：验证故障效果
    │
    ├─ 恢复阶段：清理故障、验证恢复
    │
    ├─ 收集阶段：收集产物
    │
    ▼
释放租约（状态变为 passed/failed/partial）
    │
    ▼
设备状态改为 IDLE
```

### 7.2 抢占流程

```
emergency 任务提交
    │
    ▼
Scheduler 检查保留容量
    │
    ├─ 有保留容量 → 使用保留设备
    │
    ├─ 无保留容量 → 查找可抢占任务
    │   │
    │   ├─ 找到可抢占任务（normal + interruptible）
    │   │   │
    │   │   ├─ 调用被抢占任务的 Orchestrator.on_preemption()
    │   │   │
    │   │   ├─ 原任务状态改为 PREEMPTED
    │   │   │
    │   │   ├─ 原租约状态改为 PREEMPTED
    │   │   │
    │   │   ├─ 为 emergency 创建新租约
    │   │   │
    │   │   └─ 触发 emergency 执行
    │   │
    │   └─ 没有可抢占任务 → 保持 queued
```

### 7.3 异常处理

| 异常情况 | 处理方式 |
|----------|----------|
| 设备离线（执行中） | Orchestrator 检测到离线 → 状态改为 FAILED → 记录事件 → QuarantineService 隔离设备 |
| 设备同步连续失败 | DeviceSyncService 检测 → QuarantineService 隔离设备 |
| 注入异常无法恢复 | Orchestrator 记录 → 状态改为 PARTIAL → 设备标记需人工介入 |
| 调度超时无设备 | 保持 queued 状态 → 记录等待原因 |

### 7.4 执行失败时的租约释放

Orchestrator 在任何执行结果下都必须释放租约：

```python
class ScenarioExecution:
    async def execute_with_lease(self) -> Dict[str, Any]:
        lease = self.lease_manager.get_run_lease(self.scenario_run_id)
        if not lease:
            raise ValueError("没有活跃的设备租约")

        device = lease.device
        executor = self._create_executor(device)

        try:
            result = await self.run_full_execution(executor, ...)
            return result

        except DeviceOfflineException:
            # 设备离线：隔离设备
            self.quarantine_service.quarantine_device(device, "执行中离线")
            raise

        except PreemptionException:
            # 被抢占：租约已在抢占流程中处理
            raise

        except Exception as e:
            # 其他异常：记录并标记失败
            logger.exception(f"执行异常: {e}")
            raise

        finally:
            # 确保租约被释放（除非被抢占）
            if lease.lease_status != LeaseStatus.PREEMPTED:
                self.lease_manager.release_lease(lease)
                device.status = DeviceStatus.IDLE
                self.session.commit()
```

### 7.5 边界条件处理

| 边界条件 | 处理方式 |
|----------|----------|
| 所有设备都在隔离状态 | Scheduler 检测到无可用设备 → 任务保持 QUEUED → 记录原因 "无可用设备" |
| emergency 任务无设备且无可抢占任务 | 保持 QUEUED → 记录原因 "无保留容量且无可抢占任务" |
| 设备池为空（无设备） | PoolManager 返回容量 0 → 任务保持 QUEUED |
| 租约过期（执行超时） | LeaseManager 检测过期 → 强制释放 → 任务状态改为 FAILED |
| 并发分配同一设备 | 使用数据库行级锁 `with_for_update(skip_locked=True)` |

---

## 8. API/CLI 合并设计

### 8.1 新增 API 端点

设备池管理：

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/pools/` | 获取设备池列表 |
| POST | `/api/pools/` | 创建设备池 |
| GET | `/api/pools/{id}` | 获取设备池详情 |
| PUT | `/api/pools/{id}` | 更新设备池 |
| DELETE | `/api/pools/{id}` | 删除设备池 |

设备管理（扩展）：

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/devices/sync` | 同步设备状态 |
| POST | `/api/devices/{id}/recover` | 恢复隔离设备 |
| POST | `/api/devices/{id}/quarantine` | 手动隔离设备 |

执行管理（扩展）：

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/runs/` | 创建执行（可指定 priority、pool_id） |
| GET | `/api/runs/{id}/lease` | 获取执行关联的租约信息 |
| POST | `/api/runs/{id}/cancel` | 取消执行 |

### 8.2 新增 CLI 命令

```bash
# 设备池管理
chaosdroid pool list                    # 列出设备池
chaosdroid pool create --name stable --purpose stable  # 创建设备池
chaosdroid pool show 1                  # 显示设备池详情

# 设备管理（扩展）
chaosdroid device sync                  # 同步设备状态
chaosdroid device recover --serial XXX  # 恢复隔离设备
chaosdroid device quarantine --serial XXX  # 手动隔离设备

# 执行管理（扩展）
chaosdroid run execute 1 --device auto  # 自动分配设备执行
chaosdroid run execute 1 --priority emergency  # emergency 优先级执行
chaosdroid run execute 1 --pool stable  # 指定设备池

# Worker 模式（新增）
chaosdroid worker run                   # 启动后台 Worker（含调度器和执行器）
```

---

## 9. 测试策略

### 9.1 单元测试覆盖

| 模块 | 测试重点 |
|------|----------|
| Scheduler | 任务排序、设备分配、抢占逻辑、保留容量计算 |
| PoolManager | 候选设备查询、容量计算、设备选择排序 |
| LeaseManager | 租约创建/释放/抢占、状态流转 |
| DeviceSyncService | 健康评分计算、同步逻辑、隔离触发 |
| QuarantineService | 隔离条件、恢复流程、事件记录 |
| Orchestrator | 执行流程、抢占处理、异常恢复 |

### 9.2 集成测试场景

| 场景 | 验证点 |
|------|--------|
| 普通任务执行 | 提交 → 排队 → 分配 → 执行 → 完成 |
| emergency 任务抢占 | 提交 → 检查保留容量 → 抢占 → 执行 |
| 设备离线处理 | 执行中离线 → 隔离 → 任务失败 → 恢复 |
| 批量并发执行 | 多任务提交 → 并发分配 → 并发执行 |

### 9.3 Mock 模式测试

保留 Mock 执行器，用于无真实设备环境下的完整流程验证。

---

## 10. 实施计划

### 10.1 Phase 1：基础设施层迁移（预计 2-3 天）

- 迁移 Device/DevicePool/DeviceLease 模型
- 创建 scheduling/ 子包
- 实现 Scheduler、PoolManager、LeaseManager
- 实现基础测试

### 10.2 Phase 2：模型扩展（预计 1-2 天）

- 扩展 ScenarioTemplate/ScenarioRun 模型
- 扩展枚举定义
- 数据库迁移脚本

#### 10.2.1 数据库迁移策略

整合后的数据库变更：

**新增表：**
- `devices` - 设备表
- `device_pools` - 设备池表
- `device_leases` - 设备租约表
- `incident_events` - 事件表

**修改表：**
- `scenario_templates` - 新增调度相关字段
- `scenario_runs` - 新增调度相关字段

**迁移脚本示例：**

```python
# migrations/001_add_scheduling_tables.py

def upgrade():
    # 1. 创建设备池表
    op.create_table(
        'device_pools',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(64), unique=True, nullable=False),
        sa.Column('purpose', sa.String(16), nullable=False),
        sa.Column('reserved_emergency_ratio', sa.Float(), default=0.2),
        sa.Column('max_parallel_jobs', sa.Integer()),
        sa.Column('tag_selector_json', sa.JSON()),
        sa.Column('enabled', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )

    # 2. 创建设备表
    op.create_table(
        'devices',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('serial', sa.String(64), unique=True, nullable=False),
        sa.Column('model', sa.String(128)),
        sa.Column('brand', sa.String(64)),
        sa.Column('android_version', sa.String(32)),
        sa.Column('build_fingerprint', sa.String(256)),
        sa.Column('status', sa.String(16), default='idle'),
        sa.Column('health_score', sa.Integer(), default=0),
        sa.Column('battery_level', sa.Integer()),
        sa.Column('pool_id', sa.Integer(), sa.ForeignKey('device_pools.id')),
        sa.Column('tags_json', sa.JSON()),
        sa.Column('last_seen_at', sa.DateTime()),
        sa.Column('quarantine_reason', sa.Text()),
        sa.Column('executor_mode', sa.String(8), default='mock'),
        sa.Column('sync_failure_count', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )
    op.create_index('ix_devices_status_health', 'devices', ['status', 'health_score'])

    # 3. 创建设备租约表
    op.create_table(
        'device_leases',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('device_id', sa.Integer(), sa.ForeignKey('devices.id'), nullable=False),
        sa.Column('scenario_run_id', sa.Integer(), sa.ForeignKey('scenario_runs.id')),
        sa.Column('lease_status', sa.String(16), default='active'),
        sa.Column('leased_at', sa.DateTime()),
        sa.Column('expires_at', sa.DateTime()),
        sa.Column('released_at', sa.DateTime()),
        sa.Column('preemptible', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )

    # 4. 创建事件表
    op.create_table(
        'incident_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('device_id', sa.Integer(), sa.ForeignKey('devices.id')),
        sa.Column('scenario_run_id', sa.Integer(), sa.ForeignKey('scenario_runs.id')),
        sa.Column('event_type', sa.String(32), nullable=False),
        sa.Column('severity', sa.String(16), default='info'),
        sa.Column('payload_json', sa.JSON()),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_index('ix_incident_events_event_type', 'incident_events', ['event_type'])

    # 5. 扩展 scenario_templates 表
    op.add_column('scenario_templates', sa.Column('default_priority', sa.String(16), default='normal'))
    op.add_column('scenario_templates', sa.Column('device_pool_id', sa.Integer(), sa.ForeignKey('device_pools.id')))
    op.add_column('scenario_templates', sa.Column('device_selector_json', sa.JSON()))
    op.add_column('scenario_templates', sa.Column('interruptible', sa.Boolean(), default=True))
    op.add_column('scenario_templates', sa.Column('max_concurrent', sa.Integer(), default=1))

    # 6. 扩展 scenario_runs 表
    op.add_column('scenario_runs', sa.Column('priority', sa.String(16), default='normal'))
    op.add_column('scenario_runs', sa.Column('device_pool_id', sa.Integer(), sa.ForeignKey('device_pools.id')))
    op.add_column('scenario_runs', sa.Column('device_id', sa.Integer(), sa.ForeignKey('devices.id')))
    op.add_column('scenario_runs', sa.Column('lease_id', sa.Integer(), sa.ForeignKey('device_leases.id')))
    op.add_column('scenario_runs', sa.Column('submitted_at', sa.DateTime()))
    op.add_column('scenario_runs', sa.Column('allocated_at', sa.DateTime()))
    op.add_column('scenario_runs', sa.Column('preempted_at', sa.DateTime()))
    op.add_column('scenario_runs', sa.Column('preempted_by_run_id', sa.Integer(), sa.ForeignKey('scenario_runs.id')))
    op.add_column('scenario_runs', sa.Column('interruptible', sa.Boolean(), default=True))
    op.create_index('ix_scenario_runs_status_priority_submitted', 'scenario_runs', ['status', 'priority', 'submitted_at'])

def downgrade():
    # 回滚操作...
    pass
```

**兼容性说明：**

- 新字段均有默认值，现有数据不受影响
- 现有 ScenarioRun 的 `device_serial` 字段保留，可继续使用
- 新增表不影响现有查询

### 10.3 Phase 3：编排层集成（预计 2-3 天）

- 扩展 Orchestrator 集成调度触发
- 实现抢占处理逻辑
- 实现租约释放逻辑

### 10.4 Phase 4：API/CLI 合并（预计 1-2 天）

- 新增设备池 API/CLI
- 扩展执行 API/CLI
- Web 页面更新

### 10.5 Phase 5：测试与验证（预计 2-3 天）

- 补充单元测试
- 集成测试场景
- Mock 模式完整流程验证

---

## 11. 风险与对策

| 风险 | 对策 |
|------|------|
| 两个项目代码风格差异 | 统一使用 ChaosDroid 的代码风格，Ruff 格式化 |
| 数据模型冲突 | 优先保留 ChaosDroid 原有命名，扩展而非替换 |
| 调度与编排集成复杂 | 先实现最小可用版本，逐步增加抢占等功能 |
| 并发执行竞态条件 | 使用数据库行级锁（with_for_update） |
| 原有功能回归 | 保留原有 API 接口，新增而非修改 |

---

## 12. 附录

### 12.1 保留的 ChaosDroid 模块（不改动）

- injectors/ 全部保留
- validators/ 全部保留
- observers/ 全部保留
- models/profiles.py 全部保留
- services/report_*.py 全部保留
- config/ 全部保留

### 12.2 来自 LabSentinel 的迁移清单

| LabSentinel 文件 | ChaosDroid 目标位置 |
|------------------|---------------------|
| models/device.py | models/device.py |
| models/enums.py | models/base.py（合并） |
| models/event.py | models/event.py |
| services/scheduler.py | scheduling/scheduler.py |
| services/device_sync.py | scheduling/device_sync.py |
| services/recovery.py | scheduling/quarantine.py |
| services/executor.py | 不迁移（使用 ChaosDroid 的 orchestrators） |
| services/drill.py | 不迁移 |
| services/seeds.py | services/seeds.py（改造） |