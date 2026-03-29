# ChaosDroid 技术实施报告

## 1. 技术目标

`ChaosDroid` 的目标是实现一套面向安卓设备的故障注入测试平台，用于在真实设备或模拟设备上执行受控异常场景，并验证系统的恢复能力、稳定性表现和测试链路健壮性。

第一版必须满足以下技术目标：

- 支持故障场景配置与持久化
- 支持阶段化故障注入
- 支持真实设备与模拟设备双模式执行
- 支持执行验证步骤与恢复步骤
- 支持结构化结果判定
- 支持导出 Markdown/HTML 报告

## 2. 系统架构

系统按职责分为五层：

1. `API / UI 层`
   - 提供场景管理、任务创建、结果查看和报告导出
2. `编排层`
   - 负责场景执行状态机
3. `故障注入层`
   - 负责执行 fault profile 对应动作
4. `设备执行层`
   - 对接真实设备或模拟设备
5. `观测与判定层`
   - 负责采集结果、判断注入是否成功、系统是否恢复

第一版默认单机部署，不拆分为分布式服务。

## 3. 建议目录结构

```text
chaosdroid/
  api/
  cli/
  config/
  executors/
  injectors/
  models/
  orchestrators/
  services/
  templates/
  validators/
tests/
artifacts/
```

各目录职责如下：

- `api`
  - FastAPI 接口与页面路由
- `cli`
  - Typer 命令
- `config`
  - 配置与路径管理
- `executors`
  - 设备执行器
- `injectors`
  - 故障注入实现
- `models`
  - 数据模型
- `orchestrators`
  - 场景状态机与执行流程
- `services`
  - 业务服务
- `templates`
  - 页面与报告模板
- `validators`
  - 结果判定与恢复判定

## 4. 核心数据模型

## 4.1 ScenarioTemplate

表示一个可复用的故障测试场景模板。

字段建议：

- `id`
- `name`
- `description`
- `target_type`
- `fault_profile_id`
- `inject_stage`
- `validation_profile_id`
- `recovery_profile_id`
- `executor_mode`
- `enabled`

## 4.2 FaultProfile

表示一类故障注入配置。

字段建议：

- `id`
- `name`
- `fault_type`
- `parameters_json`
- `safe_cleanup_required`
- `risk_level`

第一版 `fault_type` 固定为：

- `storage_pressure`
- `low_battery`
- `network_jitter`
- `reboot_timeout`
- `cpu_io_stress`
- `monkey_stability`

## 4.3 ValidationProfile

表示场景执行后的验证配置。

字段建议：

- `id`
- `name`
- `checks_json`
- `timeout_sec`
- `pass_rules_json`

验证项包括：

- boot 是否完成
- monkey 是否出现 fatal event
- 关键属性是否可读
- 关键进程是否存活
- 设备是否重新连通

## 4.4 RecoveryProfile

表示故障注入后的恢复策略。

字段建议：

- `id`
- `name`
- `steps_json`
- `manual_intervention_allowed`
- `timeout_sec`

恢复动作包括：

- 清理注入文件
- 重置网络
- 停止压力任务
- 重启设备
- 再次检查连通性

## 4.5 ScenarioRun

表示一次具体场景执行。

字段建议：

- `id`
- `scenario_template_id`
- `device_serial`
- `status`
- `started_at`
- `finished_at`
- `inject_stage`
- `result_summary_json`

状态固定为：

- `queued`
- `preparing`
- `injecting`
- `validating`
- `recovering`
- `passed`
- `failed`
- `partial`

## 4.6 ScenarioStep

表示一次场景执行中的单个步骤。

字段建议：

- `id`
- `scenario_run_id`
- `step_type`
- `step_order`
- `status`
- `started_at`
- `finished_at`
- `summary_json`

步骤类型固定为：

- `precheck`
- `inject`
- `observe`
- `validate`
- `recover`
- `collect`

## 4.7 Artifact

保存每次执行的日志和中间产物。

字段建议：

- `id`
- `scenario_run_id`
- `step_id`
- `artifact_type`
- `path`
- `size`
- `meta_json`

## 4.8 Report

表示最终报告。

字段建议：

- `id`
- `scenario_run_id`
- `markdown_path`
- `html_path`
- `summary_json`

## 5. 场景执行状态机

`ScenarioOrchestrator` 必须以固定状态机驱动，不允许散落在多个脚本中。

状态流如下：

1. `queued`
2. `preparing`
3. `injecting`
4. `validating`
5. `recovering`
6. `passed / failed / partial`

每个状态阶段职责如下：

### 5.1 preparing

- 检查设备在线
- 采集设备基础属性
- 检查电量、boot 状态、可用空间
- 初始化任务目录

### 5.2 injecting

- 根据 `FaultProfile` 执行注入动作
- 记录注入成功或失败
- 对需要持续存在的故障保持注入状态

### 5.3 validating

- 执行 `ValidationProfile`
- 判断系统是否表现出预期异常
- 判断核心功能是否仍然可达

### 5.4 recovering

- 执行 `RecoveryProfile`
- 检查故障是否被移除
- 检查设备是否恢复可用

### 5.5 final result

最终结果判定规则：

- 注入成功 + 验证通过 + 恢复通过 = `passed`
- 注入成功 + 验证失败 + 恢复通过 = `failed`
- 注入成功 + 验证通过 + 恢复失败 = `partial`
- 注入失败 = `failed`

## 6. 故障注入引擎设计

故障注入引擎按 `fault_type` 分派到不同 `Injector`。

统一接口：

```python
class BaseInjector:
    def prepare(self, context): ...
    def inject(self, context): ...
    def cleanup(self, context): ...
```

## 6.1 StoragePressureInjector

实现方式：

- 向目标目录写入占位文件
- 检查剩余空间变化
- 记录注入前后空间快照

验证信号：

- 可用空间明显下降
- 目标流程出现空间不足报错

恢复动作：

- 删除注入文件
- 再次检查空间恢复

## 6.2 LowBatteryInjector

真实设备上不强制做电池驱动级模拟，第一版可采用两种方式：

- 读取真实低电量设备进行验证
- 在 mock 模式中直接模拟低电量条件

项目中要明确这个边界，避免夸大能力。

## 6.3 NetworkJitterInjector

实现方式：

- mock 模式下模拟下载失败、超时、恢复
- real 模式下可通过代理层或脚本化网络开关实现有限测试

第一版允许该场景以 mock 为主。

## 6.4 RebootTimeoutInjector

实现方式：

- 在重启等待阶段注入超时条件
- 模拟设备重新上线失败或 `boot_completed` 未置位

验证信号：

- 超时
- 设备在线但系统未 ready

恢复动作：

- 再次等待
- 人工或脚本重启

## 6.5 CpuIoStressInjector

实现方式：

- 在设备上启动压力任务
- 叠加 monkey 或 boot 验证

验证信号：

- 启动延迟增加
- monkey 出现更多 crash/anr

恢复动作：

- 结束压力进程
- 重新采样状态

## 6.6 MonkeyStabilityInjector

它本质上更像一种验证型故障场景，但为了统一管理，可以在注入阶段启用 monkey 并将其结果纳入验证。

实现方式：

- 启动 monkey
- 采集输出
- 统计 crash / anr

## 7. 设备执行器设计

## 7.1 RealDeviceExecutor

职责：

- 执行 `adb` 和 shell 命令
- 读取设备属性
- 启动 monkey
- 采集日志和结果

要求：

- 所有命令通过统一封装执行
- 每个命令都记录退出码、stdout、stderr
- 支持超时控制

## 7.2 MockDeviceExecutor

职责：

- 模拟设备状态变化
- 为没有真实设备时提供稳定测试路径
- 驱动故障场景的集成测试

要求：

- 能模拟在线、离线、低电量、重启超时、空间不足、恢复成功、恢复失败

## 8. 观测与采集模块

观测模块负责采集故障注入前后和执行过程中的证据。

第一版固定采集：

- `logcat`
- `getprop` 摘要
- battery 信息
- monkey 输出
- 步骤 stdout/stderr
- 注入前后空间/状态快照

每次执行的产物路径固定为：

- `artifacts/<scenario_run_id>/`

每个步骤至少保存：

- `stdout.log`
- `stderr.log`
- `summary.json`

## 9. 结果判定模块

结果判定不能只依赖退出码，必须综合多个信号。

统一输出字段建议如下：

- `fault_injected`
- `fault_observed`
- `validation_passed`
- `recovery_passed`
- `risk_level`
- `manual_action_required`

### 判定逻辑

- 如果注入动作未生效，则 `fault_injected=false`
- 如果注入后系统没有表现出预期观测信号，则 `fault_observed=false`
- 如果验证步骤未达到预设通过标准，则 `validation_passed=false`
- 如果恢复步骤结束后设备仍不可用，则 `recovery_passed=false`

### 风险等级

第一版风险等级固定为：

- `low`
- `medium`
- `high`
- `critical`

判定依据：

- 是否影响升级链路
- 是否影响 boot
- 是否影响系统可用性
- 是否需要人工介入

## 10. Web 与 CLI 设计

## 10.1 Web 页面

最小页面集合：

- 场景列表页
- 场景详情页
- 执行记录页
- 执行详情页
- 报告查看页

页面重点是：

- 让面试官一眼看出“故障注入发生在什么阶段”
- 让执行过程和恢复过程可视化

## 10.2 CLI 命令

建议命令：

- `chaosdroid scenario list`
- `chaosdroid scenario run --name <name> --device <serial>`
- `chaosdroid worker run`
- `chaosdroid report export --run-id <id>`
- `chaosdroid device check --serial <serial>`

## 11. 报告设计

报告必须可直接作为项目展示材料使用。

每份报告固定包含：

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

Markdown 适合存档，HTML 适合演示。

## 12. 实施顺序

### 第一阶段：项目骨架

- 初始化 FastAPI、Typer、SQLAlchemy、Jinja2
- 建立基础模型
- 建立执行目录和配置体系

### 第二阶段：最小闭环

- 完成 `ScenarioTemplate`、`FaultProfile`、`ScenarioRun`
- 完成最小状态机
- 打通单场景执行与报告输出

### 第三阶段：注入器与验证器

- 实现 `StoragePressureInjector`
- 实现 `RebootTimeoutInjector`
- 实现 `CpuIoStressInjector`
- 实现基础验证器

### 第四阶段：mock 模式与页面

- 完成 `MockDeviceExecutor`
- 完成最小页面
- 完成 HTML 报告模板

### 第五阶段：补全场景与测试

- 补充 `NetworkJitterInjector`
- 补充 `MonkeyStabilityInjector`
- 编写集成测试和样本数据

## 13. 测试方案

### 13.1 单元测试

必须覆盖：

- 状态机流转
- FaultProfile 参数校验
- 注入器 prepare/inject/cleanup 逻辑
- 结果判定逻辑
- 风险等级映射

### 13.2 集成测试

必须覆盖：

- 单场景完整执行闭环
- 注入成功但恢复失败
- 注入失败直接终止
- mock 设备上的 boot 超时场景
- monkey 场景报告生成

### 13.3 验收标准

第一版至少满足：

- 支持 6 类 fault profile
- 支持 2 种执行模式
- 支持完整状态机执行
- 支持 Markdown/HTML 报告导出
- 支持 10 组以上 mock 样本回归

## 14. 实施注意事项

- 对真实设备危险较高的操作必须严格限制，特别是会导致设备不可恢复的动作。
- 第一版不建议碰 `system_server` 等高风险核心进程注入。
- 对低电量、网络波动等难以在真实设备上稳定构造的场景，必须明确标注为“mock 优先验证”。
- 项目对外表述要诚实，不夸大底层控制能力。

## 15. 结论

`ChaosDroid` 的技术价值不在于做复杂前端，也不在于做大而全的平台，而在于把故障注入测试的知识抽象成一套可配置、可执行、可复盘的系统。对测试开发岗位来说，这个项目的信号很强，因为它同时体现了系统理解、自动化能力、工程抽象能力和真实场景经验。

