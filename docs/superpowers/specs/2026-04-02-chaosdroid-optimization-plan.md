# ChaosDroid 项目优化方案

**制定日期**: 2026-04-02
**依据文档**: `reports/report_1.md`, `docs/PROJECT_REVIEW.md`

---

## 一、优化目标

基于项目审查报告识别的 20+ 项问题，按优先级分三阶段完成优化，提升项目的安全性、可维护性和功能性。

---

## 二、优化范围与优先级

### Phase 1: 安全与核心功能修复（高优先级）

**目标**: 消除安全风险，完成核心功能，确保项目可用、安全。

| 问题 | 模块 | 修复方案 | 预估工时 |
|------|------|----------|----------|
| 命令注入风险 | injectors | 参数化命令执行，验证路径安全 | 2h |
| API 未连接服务层 | api/routes | 完成所有 TODO，连接服务层 | 2h |
| 注入器状态管理 | injectors | 状态移至 InjectContext | 2h |
| 设备锁定机制 | services | 实现 acquire/release 锁 | 2h |

**验收标准**:
- [ ] 所有 shell 命令使用参数化执行
- [ ] 所有 API 端点返回真实数据
- [ ] 注入器无实例状态污染
- [ ] 设备锁防止并发冲突

---

### Phase 2: 代码质量提升（中优先级）

**目标**: 提升代码可维护性，消除技术债务。

| 问题 | 模块 | 修复方案 | 预估工时 |
|------|------|----------|----------|
| 枚举重复定义 | models/base.py | 统一到 models/base.py | 1h |
| 缺少数据库索引 | models/*.py | 添加高频查询字段索引 | 1h |
| 服务层职责过重 | services/ | 拆分为小服务类 | 3h |
| 认证授权缺失 | api/ | 添加 API Key 中间件 | 2h |
| 超时处理不完善 | orchestrators/ | 完善阶段超时处理 | 2h |

**验收标准**:
- [ ] 所有枚举统一定义在 models/base.py
- [ ] scenario_runs、devices 等表有索引
- [ ] ExecutionService 拆分为 3-4 个小服务
- [ ] API 支持 Key 验证
- [ ] 各阶段有超时保护和清理逻辑

---

### Phase 3: 增强功能（低优先级）

**目标**: 完善测试、日志和文档，提升项目完成度。

| 问题 | 模块 | 修复方案 | 预估工时 |
|------|------|----------|----------|
| 日志格式不灵活 | config/logging.py | 支持配置文件自定义 | 1h |
| Mock 日志不真实 | executors/mock_executor.py | 生成模拟 logcat | 1h |
| 测试数据管理 | tests/ | 实现测试数据工厂 | 2h |
| 集成测试不足 | tests/ | 添加端到端测试 | 2h |
| 文档不完善 | docs/ | 补充 API 文档和示例 | 2h |

**验收标准**:
- [ ] 日志格式可通过配置文件修改
- [ ] Mock 执行器返回真实感日志
- [ ] 测试使用工厂模式创建数据
- [ ] 至少 3 个端到端集成测试
- [ ] README 包含完整使用示例

---

## 三、实施顺序

```
Phase 1 (安全与核心功能)
    │
    ├─ 1.1 命令注入修复
    ├─ 1.2 API 连接服务层
    ├─ 1.3 注入器状态管理
    └─ 1.4 设备锁定机制
    │
    ▼
Phase 2 (代码质量提升)
    │
    ├─ 2.1 枚举统一
    ├─ 2.2 数据库索引
    ├─ 2.3 服务层拆分
    ├─ 2.4 认证授权
    └─ 2.5 超时处理
    │
    ▼
Phase 3 (增强功能)
    │
    ├─ 3.1 日志增强
    ├─ 3.2 Mock 日志模拟
    ├─ 3.3 测试数据工厂
    ├─ 3.4 集成测试
    └─ 3.5 文档完善
```

---

## 四、技术细节

### 4.1 命令注入修复

**当前风险代码**:
```python
cmd = f"dd if=/dev/zero of='{file_path}' bs=1M count={chunk_size_mb}"
result = await executor.execute_shell(cmd, timeout=120)
```

**修复方案**:
```python
# 使用参数化命令（如果 executor 支持）
result = await executor.execute_shell(
    "dd",
    ["if=/dev/zero", f"of={validated_path}", "bs=1M", str(chunk_size_mb)]
)
```

如果 `execute_shell` 只接受字符串，则确保：
1. 路径经过 `_validate_path()` 验证
2. 使用单引号包裹路径
3. 拒绝包含 shell 元字符的路径

---

### 4.2 枚举统一

**整合后的 models/base.py 枚举**:
```python
# ChaosDroid 原有枚举
class RunStatus(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    INJECTING = "injecting"
    VALIDATING = "validating"
    RECOVERING = "recovering"
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    ALLOCATING = "allocating"
    RESERVED = "reserved"
    PREEMPTED = "preempted"

class FaultType(str, Enum):
    storage_pressure = "storage_pressure"
    low_battery = "low_battery"
    network_jitter = "network_jitter"
    reboot_timeout = "reboot_timeout"
    cpu_io_stress = "cpu_io_stress"
    monkey_stability = "monkey_stability"

# LabSentinel 新增枚举
class DeviceStatus(str, Enum):
    IDLE = "idle"
    RESERVED = "reserved"
    BUSY = "busy"
    OFFLINE = "offline"
    QUARANTINED = "quarantined"
    RECOVERING = "recovering"

class LeaseStatus(str, Enum):
    ACTIVE = "active"
    RELEASED = "released"
    PREEMPTED = "preempted"
    EXPIRED = "expired"

class Priority(str, Enum):
    NORMAL = "normal"
    HIGH = "high"
    EMERGENCY = "emergency"
```

---

### 4.3 数据库索引

**需要添加索引的表**:
```python
# scenario_runs
__table_args__ = (
    Index('ix_scenario_runs_status', 'status'),
    Index('ix_scenario_runs_scenario_template_id', 'scenario_template_id'),
    Index('ix_scenario_runs_device_serial', 'device_serial'),
    Index('ix_scenario_runs_status_priority_submitted', 'status', 'priority', 'submitted_at'),
)

# devices
__table_args__ = (
    Index('ix_devices_status', 'status'),
    Index('ix_devices_serial', 'serial'),
    Index('ix_devices_status_health', 'status', 'health_score'),
)

# device_leases
__table_args__ = (
    Index('ix_device_leases_device_id', 'device_id'),
    Index('ix_device_leases_scenario_run_id', 'scenario_run_id'),
    Index('ix_device_leases_status', 'lease_status'),
)
```

---

### 4.4 服务层拆分

**原 ExecutionService 拆分为**:

| 新服务 | 职责 |
|--------|------|
| ScenarioOrchestratorService | 编排执行流程 |
| InjectorDispatchService | 注入器选择和调用 |
| ValidationService | 验证逻辑 |
| RecoveryService | 恢复逻辑 |
| ObservationService | 观测数据采集 |

---

## 五、测试策略

### 5.1 单元测试

每个修复点必须有对应的单元测试：
- 命令注入：测试非法路径被拒绝
- API 连接：测试端点返回真实数据
- 枚举统一：测试所有引用点正常工作
- 索引添加：测试查询性能（可选）

### 5.2 集成测试

- 完整执行流程：提交→排队→分配→执行→完成
- 抢占流程：emergency 任务抢占 normal 任务
- 设备离线处理：执行中离线→隔离→恢复

---

## 六、验收清单

### Phase 1 验收
- [ ] 所有注入器路径验证通过 `_validate_path()`
- [ ] API 端点 `/api/runs/` 返回数据库数据
- [ ] 注入器不使用实例状态存储
- [ ] 设备锁测试通过

### Phase 2 验收
- [ ] 只有一个 `models/base.py` 定义所有枚举
- [ ] 数据库查询使用索引
- [ ] ExecutionService 拆分为小服务
- [ ] API 支持 `X-API-Key` 头验证
- [ ] 超时触发清理逻辑

### Phase 3 验收
- [ ] 日志格式可配置
- [ ] Mock 执行器返回模拟 logcat
- [ ] 测试使用工厂模式
- [ ] 3 个端到端测试通过
- [ ] README 包含使用示例

---

## 七、风险与对策

| 风险 | 对策 |
|------|------|
| API 变更导致不兼容 | 保留原接口签名，内部实现替换 |
| 数据库迁移影响现有数据 | 所有新字段加默认值 |
| 服务拆分破坏现有调用 | 先添加新服务，逐步迁移调用点 |
| 测试覆盖率下降 | 每个改动必须有对应测试 |

---

## 八、时间估算

| 阶段 | 预估工时 | 备注 |
|------|----------|------|
| Phase 1 | 8h | 1 个工作日 |
| Phase 2 | 9h | 1-2 个工作日 |
| Phase 3 | 8h | 1 个工作日 |
| **总计** | **25h** | 约 3-4 个工作日 |

---

**下一步**: 等待用户审批此方案后，开始执行 Phase 1。
