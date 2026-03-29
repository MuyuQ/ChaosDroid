# ChaosDroid 设计规范

## 1. 项目概述

ChaosDroid 是一个面向安卓设备的故障注入测试与恢复验证平台。核心目标是将故障注入测试流程产品化，支持在可控条件下制造异常，验证系统的鲁棒性和恢复能力。

### 1.1 核心功能

- 支持定义标准化故障注入场景
- 支持在指定阶段执行故障注入
- 支持真实设备和模拟设备两种模式
- 支持执行验证步骤并收集观测信息
- 支持执行恢复动作并判断恢复结果
- 支持生成可读的 Markdown/HTML 报告

### 1.2 技术栈

| 组件 | 选择 | 说明 |
|------|------|------|
| Web框架 | FastAPI | 异步支持，自动API文档 |
| CLI框架 | Typer | 现代Python命令行工具 |
| ORM | SQLAlchemy 2.0 | 支持异步，配置切换数据库 |
| 数据库 | SQLite | 开发和生产都用，单机部署 |
| 模板 | Jinja2 + HTMX | 轻量前端，无需构建 |
| 校验 | Pydantic v2 | 场景配置和结果校验 |
| 异步任务 | asyncio + BackgroundTasks | Web后台执行 |

## 2. 系统架构

系统按职责分为五层：

1. **API/UI层** - 提供场景管理、任务创建、结果查看和报告导出
2. **编排层** - 负责场景执行状态机
3. **故障注入层** - 负责执行 fault profile 对应动作
4. **设备执行层** - 对接真实设备或模拟设备
5. **观测与判定层** - 负责采集结果、判断注入是否成功、系统是否恢复

### 2.1 执行模式

采用混合模式：
- **CLI命令** - 同步执行，实时输出，方便调试
- **Web触发** - 异步后台执行，不阻塞UI，支持查看进度

## 3. 目录结构

```
chaosdroid/
├── api/                    # FastAPI 路由和页面
│   ├── routes/
│   ├── templates/
│   └── main.py
├── cli/                    # Typer 命令
├── config/                 # 配置管理
├── models/                 # SQLAlchemy 数据模型
├── orchestrators/          # 执行编排和状态机
├── injectors/              # 故障注入实现
├── executors/              # 设备执行器
├── validators/             # 结果判定
├── services/               # 业务服务层
├── observers/              # 观测采集
├── templates/              # 报告模板
├── artifacts/              # 执行产物存储
├── tests/                  # 测试
├── main.py                 # 统一入口
└── pyproject.toml
```

## 4. 数据模型

### 4.1 ScenarioTemplate

场景模板，可复用的故障测试场景。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| name | str | 场景名称 |
| description | str | 场景描述 |
| target_type | str | 目标类型 |
| fault_profile_id | int | 关联故障配置 |
| inject_stage | str | 注入阶段 |
| validation_profile_id | int | 关联验证配置 |
| recovery_profile_id | int | 关联恢复配置 |
| executor_mode | str | real/mock |
| enabled | bool | 是否启用 |

### 4.2 FaultProfile

故障注入配置。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| name | str | 配置名称 |
| fault_type | str | 故障类型 |
| parameters_json | str | 参数JSON |
| safe_cleanup_required | bool | 是否需要安全清理 |
| risk_level | str | 风险等级 |

故障类型固定为：
- `storage_pressure` - 存储压力
- `low_battery` - 低电量
- `network_jitter` - 网络波动
- `reboot_timeout` - 重启超时
- `cpu_io_stress` - CPU/I/O压力
- `monkey_stability` - Monkey稳定性

### 4.3 ValidationProfile

验证配置。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| name | str | 配置名称 |
| checks_json | str | 检查项JSON |
| timeout_sec | int | 超时时间 |
| pass_rules_json | str | 通过规则JSON |

验证项包括：boot完成、monkey fatal event、关键属性可读、关键进程存活、设备重新连通。

### 4.4 RecoveryProfile

恢复策略配置。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| name | str | 配置名称 |
| steps_json | str | 恢复步骤JSON |
| manual_intervention_allowed | bool | 是否允许人工介入 |
| timeout_sec | int | 超时时间 |

恢复动作包括：清理注入文件、重置网络、停止压力任务、重启设备、检查连通性。

### 4.5 ScenarioRun

场景执行记录。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| scenario_template_id | int | 关联场景模板 |
| device_serial | str | 设备序列号 |
| status | str | 执行状态 |
| started_at | datetime | 开始时间 |
| finished_at | datetime | 结束时间 |
| inject_stage | str | 注入阶段 |
| result_summary_json | str | 结果摘要JSON |

状态：`queued`, `preparing`, `injecting`, `validating`, `recovering`, `passed`, `failed`, `partial`。

### 4.6 ScenarioStep

执行步骤记录。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| scenario_run_id | int | 关联执行记录 |
| step_type | str | 步骤类型 |
| step_order | int | 步骤顺序 |
| status | str | 步骤状态 |
| started_at | datetime | 开始时间 |
| finished_at | datetime | 结束时间 |
| summary_json | str | 步骤摘要JSON |

步骤类型：`precheck`, `inject`, `observe`, `validate`, `recover`, `collect`。

### 4.7 Artifact

执行产物。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| scenario_run_id | int | 关联执行记录 |
| step_id | int | 关联步骤 |
| artifact_type | str | 产物类型 |
| path | str | 文件路径 |
| size | int | 文件大小 |
| meta_json | str | 元数据JSON |

### 4.8 Report

报告记录。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| scenario_run_id | int | 关联执行记录 |
| markdown_path | str | Markdown路径 |
| html_path | str | HTML路径 |
| summary_json | str | 摘要JSON |

## 5. 状态机设计

### 5.1 状态流转

```
queued -> preparing -> injecting -> validating -> recovering -> passed/failed/partial
```

### 5.2 各阶段职责

**preparing**
- 检查设备在线
- 采集设备基础属性
- 检查电量、boot状态、可用空间
- 初始化任务目录

**injecting**
- 根据 FaultProfile 执行注入动作
- 记录注入成功或失败
- 对需要持续存在的故障保持注入状态

**validating**
- 执行 ValidationProfile
- 判断系统是否表现出预期异常
- 判断核心功能是否仍然可达

**recovering**
- 执行 RecoveryProfile
- 检查故障是否被移除
- 检查设备是否恢复可用

**final result**
- 注入成功 + 验证通过 + 恢复通过 = `passed`
- 注入成功 + 验证失败 + 恢复通过 = `failed`
- 注入成功 + 验证通过 + 恢复失败 = `partial`
- 注入失败 = `failed`

### 5.3 实现方式

采用显式状态模式，每个状态对应一个处理函数：

```python
class ScenarioOrchestrator:
    def run(self, scenario_run_id: int) -> RunStatus:
        while scenario_run.status in STATE_HANDLERS:
            next_status = STATE_HANDLERS[scenario_run.status](scenario_run)
            scenario_run.status = next_status
            db.commit()
        return scenario_run.status
```

## 6. 故障注入引擎

### 6.1 基类接口

```python
class BaseInjector(ABC):
    fault_type: str

    @abstractmethod
    def prepare(self, context: InjectContext) -> bool: pass

    @abstractmethod
    def inject(self, context: InjectContext) -> InjectResult: pass

    @abstractmethod
    def cleanup(self, context: InjectContext) -> bool: pass
```

### 6.2 注册机制

```python
INJECTOR_REGISTRY: dict[str, BaseInjector] = {}

def get_injector(fault_type: str) -> BaseInjector:
    return INJECTOR_REGISTRY[fault_type]
```

### 6.3 六类注入器实现要点

**StoragePressureInjector**
- 向目标目录写入占位文件
- 检查剩余空间变化
- 恢复：删除注入文件

**LowBatteryInjector**
- Real模式：读取真实低电量设备状态
- Mock模式：模拟低电量条件

**NetworkJitterInjector**
- Mock模式：模拟下载失败、超时、恢复
- Real模式：通过代理层实现有限测试

**RebootTimeoutInjector**
- 在重启等待阶段注入超时条件
- Mock模式：模拟boot_completed未置位
- 恢复：再次等待或重启

**CpuIoStressInjector**
- 在设备上启动压力任务
- 恢复：结束压力进程

**MonkeyStabilityInjector**
- 启动monkey，采集输出
- 统计crash/ANR

## 7. 设备执行器

### 7.1 统一接口

```python
class BaseDeviceExecutor(ABC):
    def is_online(self) -> bool: pass
    def get_properties(self) -> dict[str, str]: pass
    def get_storage_info(self) -> StorageInfo: pass
    def get_battery_info(self) -> BatteryInfo: pass
    def execute_shell(self, cmd: str, timeout: int) -> ShellResult: pass
    def push_file(self, local: str, remote: str) -> bool: pass
    def pull_file(self, remote: str, local: str) -> bool: pass
    def run_monkey(self, package: str, count: int, options: dict) -> MonkeyResult: pass
    def reboot(self, wait_timeout: int) -> bool: pass
```

### 7.2 Mock模式场景

- `normal` - 正常设备
- `offline` - 设备离线
- `low_battery` - 低电量
- `storage_full` - 存储不足
- `boot_timeout` - 重启超时
- `network_error` - 网络错误

## 8. 观测采集

固定采集内容：
- logcat
- getprop摘要
- battery信息
- monkey输出
- 步骤stdout/stderr
- 注入前后状态快照

产物路径：`artifacts/<scenario_run_id>/`

每个步骤保存：`stdout.log`, `stderr.log`, `summary.json`

## 9. 结果判定

### 9.1 判定字段

- `fault_injected` - 注入是否生效
- `fault_observed` - 故障是否被观测到
- `validation_passed` - 验证是否通过
- `recovery_passed` - 恢复是否成功
- `risk_level` - 风险等级
- `manual_action_required` - 是否需要人工介入

### 9.2 风险等级

- `low` - 不影响关键链路
- `medium` - 影响升级链路
- `high` - 影响boot或系统可用性
- `critical` - 需要人工介入恢复

## 10. Web页面

| 页面 | 路径 | 功能 |
|------|------|------|
| 场景列表 | /scenarios | 新建、编辑、克隆、启用/禁用 |
| 场景详情 | /scenarios/{id} | 配置详情、关联执行记录 |
| 执行列表 | /runs | 筛选状态、场景、设备 |
| 执行详情 | /runs/{id} | 过程、步骤结果、artifacts |
| 报告查看 | /reports/{id} | HTML报告，下载Markdown |

使用HTMX实现交互，无需复杂JavaScript。

## 11. CLI命令

```bash
chaosdroid scenario list
chaosdroid scenario create --name <name> --fault-type <type>
chaosdroid run <scenario-id> --device <serial> --mode real/mock
chaosdroid runs list --status failed --limit 10
chaosdroid report export <run-id> --format html --output ./reports/
chaosdroid device check <serial>
chaosdroid serve --port 8000
```

## 12. 报告内容

每份报告包含：
- 场景名称
- 设备信息
- 注入阶段
- 故障类型
- 注入动作摘要
- 验证动作摘要
- 恢复动作摘要
- 最终结论
- 风险等级
- 关键证据
- 建议动作

## 13. 注入阶段定义

故障注入绑定到固定阶段，保证触发点可复现：

| 阶段 | 说明 | 适用场景 |
|------|------|----------|
| precheck | 前置检查阶段 | 低电量阻断、存储空间检查 |
| prepare | 准备阶段 | 环境配置时注入 |
| upgrading | 升级进行中 | 网络中断、存储压力 |
| reboot_wait | 重启等待 | boot超时、掉线模拟 |
| post_boot | 启动后 | monkey稳定性、CPU压力 |
| post_validate | 验证后 | 恢复验证阶段 |

阶段化注入确保：
- 故障触发点可复现
- 报告中的结论有上下文
- 同类场景可横向比较

## 14. 数据模型补充

### 14.1 通用字段

所有模型增加时间戳：
- `created_at` - 创建时间
- `updated_at` - 更新时间

### 14.2 外键关系

```
ScenarioTemplate
  ├── fault_profile_id -> FaultProfile
  ├── validation_profile_id -> ValidationProfile
  └── recovery_profile_id -> RecoveryProfile

ScenarioRun
  ├── scenario_template_id -> ScenarioTemplate
  └── steps -> ScenarioStep[]

ScenarioStep
  ├── scenario_run_id -> ScenarioRun
  └── artifacts -> Artifact[]

Artifact
  ├── scenario_run_id -> ScenarioRun
  └ step_id -> ScenarioStep

Report
  └── scenario_run_id -> ScenarioRun
```

### 14.3 target_type 可选值

| 值 | 说明 |
|------|------|
| upgrade | 升级链路测试 |
| stability | 稳定性测试 |
| monkey | Monkey压测 |
| recovery | 恢复能力验证 |

## 15. 错误处理与超时机制

### 15.1 各阶段默认超时

| 阶段 | 默认超时 | 可配置 |
|------|----------|--------|
| preparing | 60s | 是 |
| injecting | 120s | 是 |
| validating | 180s | 是 |
| recovering | 300s | 是 |

### 15.2 异常处理策略

- **注入失败** - 立即进入 recovering 状态尝试清理
- **超时** - 记录超时事件，标记步骤失败，继续后续阶段
- **设备离线** - 等待重连超时后标记失败
- **不可恢复错误** - 标记 `failed`，记录人工介入需求

### 15.3 数据库事务

- 每个状态转换后立即 commit
- 步骤内的多步操作使用事务包装
- 失败时回滚步骤内操作，保留状态记录

## 16. 配置体系

### 16.1 配置文件

配置文件路径：`config/settings.py`，使用 Pydantic BaseSettings：

```python
class Settings(BaseSettings):
    database_path: str = "chaosdroid.db"
    artifacts_dir: str = "artifacts/"
    reports_dir: str = "reports/"
    adb_path: str = "adb"
    default_timeout: int = 120
    web_port: int = 8000
    log_level: str = "INFO"

    class Config:
        env_prefix = "CHAOSDROID_"  # 支持环境变量
```

### 16.2 可配置项

| 配置项 | 环境变量 | 默认值 |
|------|----------|--------|
| database_path | CHAOSDROID_DATABASE_PATH | chaosdroid.db |
| artifacts_dir | CHAOSDROID_ARTIFACTS_DIR | artifacts/ |
| reports_dir | CHAOSDROID_REPORTS_DIR | reports/ |
| adb_path | CHAOSDROID_ADB_PATH | adb |
| default_timeout | CHAOSDROID_DEFAULT_TIMEOUT | 120 |
| web_port | CHAOSDROID_WEB_PORT | 8000 |
| log_level | CHAOSDROID_LOG_LEVEL | INFO |

## 17. REST API 设计

### 17.1 场景管理

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | /api/scenarios | 场景列表 |
| POST | /api/scenarios | 创建场景 |
| GET | /api/scenarios/{id} | 场景详情 |
| PUT | /api/scenarios/{id} | 更新场景 |
| DELETE | /api/scenarios/{id} | 删除场景 |
| POST | /api/scenarios/{id}/clone | 克隆场景 |

### 17.2 执行管理

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | /api/runs | 执行列表（支持筛选） |
| POST | /api/runs | 创建执行记录 |
| GET | /api/runs/{id} | 执行详情 |
| POST | /api/runs/{id}/execute | 触发执行（异步） |
| DELETE | /api/runs/{id} | 取消执行 |

### 17.3 报告管理

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | /api/reports/{id} | 获取报告元数据 |
| GET | /api/reports/{id}/html | 获取HTML报告 |
| GET | /api/reports/{id}/markdown | 获取Markdown报告 |

### 17.4 设备管理

| 方法 | 端点 | 功能 |
|------|------|------|
| GET | /api/devices | 设备列表 |
| GET | /api/devices/{serial}/check | 检查设备状态 |

### 17.5 响应格式

```json
{
  "success": true,
  "data": {...},
  "error": null
}
```

错误响应：
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "DEVICE_OFFLINE",
    "message": "设备不在线",
    "details": {...}
  }
}
```

## 18. 安全设计

### 18.1 命令注入防护

- 所有 shell 命令参数必须经过校验
- 禁止直接拼接用户输入到命令字符串
- 使用参数化方式传递命令

```python
# 禁止
cmd = f"rm {user_path}"

# 推荐
result = executor.execute_shell("rm", [validated_path])
```

### 18.2 危险操作确认

以下操作需要显式确认：
- 重启设备 (`reboot`)
- 清理存储 (`rm -rf`)
- 停止系统进程

配置中增加 `dangerous_operations_require_confirm: bool = True`

### 18.3 真实设备操作风险提示

- 注入前显示风险等级和预期影响
- 恢复失败时明确提示人工介入需求
- 记录所有操作日志供审计

## 19. 部署说明

### 19.1 安装

```bash
pip install chaosdroid
```

或从源码：
```bash
git clone <repo>
cd chaosdroid
pip install -e .
```

### 19.2 初始化

```bash
chaosdroid init  # 创建数据库和目录结构
```

### 19.3 启动服务

```bash
chaosdroid serve --port 8000
```

### 19.4 日志配置

- 日志文件：`logs/chaosdroid.log`
- 按日期滚动
- 可通过 `log_level` 配置调整

## 20. 场景克隆实现

克隆场景时：
- 复制 ScenarioTemplate 所有字段
- 生成新名称（原名称 + "-clone" 或用户指定）
- 关联的 Profile 不复制，共享引用
- 设置 `enabled=False`，需用户手动启用

```python
def clone_scenario(template_id: int, new_name: str = None) -> ScenarioTemplate:
    original = db.get(ScenarioTemplate, template_id)
    clone = ScenarioTemplate(
        name=new_name or f"{original.name}-clone",
        description=original.description,
        fault_profile_id=original.fault_profile_id,
        ...
        enabled=False
    )
    db.add(clone)
    return clone
```

## 21. 批量执行策略

### 21.1 执行模式

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| sequential | 顺序执行，一个完成再下一个 | 调试、单设备 |
| concurrent | 并发执行，指定并发数 | 多设备批量测试 |

### 21.2 并发控制

```python
class BatchExecutor:
    max_concurrent: int = 3  # 最大并发数
    semaphore: asyncio.Semaphore

    async def run_batch(self, scenario_ids: list[int], devices: list[str]):
        tasks = [
            self._run_with_semaphore(id, device)
            for id, device in zip(scenario_ids, devices)
        ]
        await asyncio.gather(*tasks)
```

### 21.3 资源管理

- 每个设备同时只能执行一个场景
- 防止同一设备被多个任务占用
- 设备占用状态跟踪

## 22. Mock设备状态管理

### 22.1 状态持久化

Mock设备需要跨步骤保持状态：

```python
class MockDeviceState:
    online: bool = True
    battery_level: int = 100
    storage_available: int = 1024 * 1024 * 1024  # 1GB
    boot_completed: bool = True
    network_connected: bool = True
    stress_processes: list[str] = []

    def apply_injection(self, fault_type: str, params: dict):
        # 根据故障类型修改状态
        ...

    def apply_recovery(self, step: str):
        # 恢复状态
        ...
```

### 22.2 时间模拟

```python
# 模拟操作耗时
async def execute_shell(self, cmd: str, timeout: int) -> ShellResult:
    await asyncio.sleep(random.uniform(0.1, 0.5))  # 模拟延迟
    return self._mock_result(cmd)
```

## 23. 实施阶段

### 阶段1：项目骨架
- 初始化项目结构、pyproject.toml
- 建立数据库模型
- 建立配置体系

### 阶段2：最小闭环
- 完成核心模型CRUD
- 完成状态机框架
- 打通StoragePressure完整流程
- 输出基础报告

### 阶段3：注入器与验证器
- 实现6个注入器
- 实现验证器和判定器
- 完善观测采集

### 阶段4：Mock模式与页面
- 完成MockDeviceExecutor
- 完成Web页面
- 完善HTML报告模板

### 阶段5：测试与完善
- 单元测试覆盖
- 集成测试覆盖
- 10组mock样本回归

## 14. 测试方案

### 14.1 单元测试覆盖
- 状态机流转
- FaultProfile参数校验
- 注入器prepare/inject/cleanup
- 结果判定逻辑
- 风险等级映射

### 14.2 集成测试覆盖
- 单场景完整闭环
- 注入成功恢复失败
- 注入失败终止
- mock设备boot超时
- monkey场景报告生成

### 14.3 验收标准
- 支持6类fault profile
- 支持2种执行模式
- 支持完整状态机
- 支持Markdown/HTML报告
- 10组以上mock样本回归