# ChaosDroid-TraceLens 集成使用指南

**集成完成日期**: 2026-04-03
**ChaosDroid 版本**: 0.1.0

---

## 概述

ChaosDroid 与 TraceLens 的集成实现了故障注入测试完成后的自动日志导出和诊断分析功能。

### 核心功能

1. **自动触发**: 任务执行完成后自动发布事件
2. **异步处理**: 基于 SQLite 队列的解耦架构
3. **完整日志**: 导出 logcat + 设备快照 + Android 系统日志目录
4. **智能诊断**: 使用规则引擎分析故障根因
5. **结果展示**: Web UI 显示诊断摘要和详情链接

### 16 种诊断类别

支持的故障分类：bootloop, system_crash, hal_crash, kernel_panic, watchdog, security, audio, camera, connectivity, display, power, performance, stability, filesystem, memory, custom

---

## 相关文档

- 快速开始：[README.md](../../README.md)
- 部署指南：[DEPLOY.md](../../DEPLOY.md)
- 详细部署：[DEPLOYMENT.md](../../DEPLOYMENT.md)

---

## 架构组件

### 数据模型

| 模型 | 文件路径 | 说明 |
|------|---------|------|
| `EventQueue` | `app/models/event_queue.py` | 事件队列表 |
| `ScenarioRun` (扩展) | `app/models/scenario.py` | 添加 5 个诊断字段 |

### 服务层

| 服务 | 文件路径 | 说明 |
|------|---------|------|
| `EventDispatcher` | `app/services/event_dispatcher.py` | 发布事件到队列 |
| `LogExportService` | `app/services/log_export_service.py` | 导出设备日志 |
| `DiagnosisTrigger` | `app/diagnosis/services/trigger.py` | 诊断触发器 |
| `IngestService` | `app/diagnosis/services/ingest.py` | 导入日志到诊断系统 |
| `DiagnoseService` | `app/diagnosis/services/diagnose.py` | 执行诊断分析 |

### 后台 Worker

| Worker | 文件路径 | 说明 |
|--------|---------|------|
| `DiagnosisWorker` | `app/workers/diagnosis_worker.py` | 轮询队列（5 秒间隔） |

---

## 数据流

```
1. ExecutionService.execute_scenario() 完成
       │
       ▼
2. EventDispatcher.publish_run_completed() 发布事件
       │
       ▼
3. EventQueue 表 (status=pending)
       │
       ▼
4. DiagnosisWorker 轮询 (每 5 秒)
       │
       ▼
5. DiagnosisTrigger 处理
       ├── LogExportService → artifacts/diagnosis/{run_id}/
       ├── IngestService → DiagnosticRun
       ├── DiagnoseService → RuleEngine
       └── 更新 ScenarioRun.diagnosis_* 字段
```

---

## 使用方式

### 1. 启动服务

```bash
python start_server.py
# 或
python -m app.api.main
```

DiagnosisWorker 会在应用启动时自动运行。

### 2. 执行测试任务

```bash
# 通过 API 执行
curl -X POST http://localhost:8000/api/runs/execute \
  -H "X-API-Key: your-api-key" \
  -d '{"scenario_template_id": 1, "device_serial": "emulator-5554"}'

# 或通过 Web UI
# 访问 http://localhost:8000/scenarios 并点击执行
```

### 3. 查看诊断结果

任务完成后，访问任务详情页：
```
http://localhost:8000/runs/{run_id}
```

诊断结果面板将显示：
- 诊断分类（徽章形式）
- 根因描述
- 置信度（百分比）
- 完成时间
- 查看详情按钮

---

## 导出目录结构

```
artifacts/
└── diagnosis/
    └── {scenario_run_id}/
        ├── logcat.log                    # logcat 日志
        ├── snapshot.json                 # 设备状态快照
        └── android_logs/                 # Android 系统日志（需要 root）
            ├── log/                      # /data/log/
            ├── tombstones/               # /tombstones/
            └── anr/                      # /data/anr/
```

---

## 数据库迁移

首次使用前执行迁移：

```bash
python migrations/001_tracelens_integration.py
```

或使用 Alembic（如果已配置）：

```bash
alembic upgrade head
```

---

## 配置项

通过环境变量配置诊断模块：

```bash
# 配置前缀
CHAOSDROID_DIAGNOSIS_

# 示例
CHAOSDROID_DIAGNOSIS_DATABASE_URL=sqlite+aiosqlite:///chaosdroid.db
CHAOSDROID_DIAGNOSIS_ARTIFACTS_BASE_PATH=artifacts/raw
CHAOSDROID_DIAGNOSIS_RULES_PATH=app/diagnosis/rules
```

---

## 诊断分类

支持的故障分类（16 种）：

| 分类 | 说明 |
|------|------|
| `bootloop` | 系统启动循环检测 |
| `system_crash` | 系统服务崩溃 |
| `hal_crash` | 硬件抽象层崩溃 |
| `kernel_panic` | 内核崩溃 |
| `watchdog` | 看门狗超时 |
| `security` | 安全模块异常 |
| `audio` | 音频系统问题 |
| `camera` | 相机系统问题 |
| `connectivity` | 连接性问题 |
| `display` | 显示系统问题 |
| `power` | 电源管理问题 |
| `performance` | 性能问题 |
| `stability` | 稳定性问题 |
| `filesystem` | 文件系统问题 |
| `memory` | 内存问题 |
| `custom` | 自定义规则 |

---

## 故障排查

### 诊断任务未执行

1. 检查 DiagnosisWorker 是否启动：
   ```bash
   # 查看日志
   tail -f logs/chaosdroid.log | grep DiagnosisWorker
   ```

2. 检查队列中是否有 pending 事件：
   ```bash
   # 使用 SQLite 客户端
   sqlite3 chaosdroid.db "SELECT * FROM event_queue WHERE status = 'pending';"
   ```

### 日志导出失败

1. 检查设备是否在线：
   ```bash
   adb devices
   ```

2. 检查 root 权限（可选）：
   ```bash
   adb shell su -c 'echo rooted'
   ```

### 诊断结果为空

1. 检查规则文件是否存在：
   ```bash
   ls -la app/diagnosis/rules/
   ```

2. 检查诊断数据库：
   ```bash
   sqlite3 data/tracelens.db "SELECT * FROM diagnostic_runs ORDER BY created_at DESC LIMIT 1;"
   ```

---

## 诊断 API

### 手动触发诊断

```bash
curl -X POST http://localhost:8000/api/diagnosis/trigger \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"device_serial": "emulator-5554", "event_type": "fault_injection_complete"}'
```

### 查询诊断结果

```bash
curl http://localhost:8000/api/diagnosis/result/{diagnosis_id} \
  -H "X-API-Key: your-api-key"
```

### 列出诊断记录

```bash
curl "http://localhost:8000/api/diagnosis/list?device_serial=emulator-5554" \
  -H "X-API-Key: your-api-key"
```

---

## 测试

运行集成测试：

```bash
pytest app/tests/test_tracelens_integration.py -v
```

测试用例：
- `test_event_dispatcher_publish` - 事件发布
- `test_event_queue_model` - 队列模型
- `test_diagnosis_trigger_poll` - 诊断轮询
- `test_scenario_run_diagnosis_fields` - 诊断字段

---

## 扩展开发

### 添加新的诊断规则

在 `app/diagnosis/rules/core_rules.yaml` 中添加规则。

### 自定义日志导出

继承 `LogExportService` 并重写 `export_full_snapshot()` 方法。

### 修改 Worker 配置

编辑 `app/api/main.py` 中的 `DiagnosisWorker` 初始化参数：

```python
_diagnosis_worker = DiagnosisWorker(
    poll_interval_sec=5,    # 轮询间隔
    batch_size=10,          # 批次大小
)
```

---

## 注意事项

1. **Root 权限**: Android 系统日志目录（`/data/log/`、`/tombstones/`、`/data/anr/`）需要 root 权限
2. **降级处理**: 无 root 权限时仅导出 logcat 和设备快照
3. **设备离线**: 优先使用 `ObservationCollector` 已收集的 artifacts
4. **诊断失败**: 不影响原任务状态，仅记录错误日志

---

## 相关资源

- 主文档：[README.md](../../README.md)
- 部署指南：[DEPLOY.md](../../DEPLOY.md)
- 详细部署：[DEPLOYMENT.md](../../DEPLOYMENT.md)
- 项目仓库：https://github.com/chaosdroid/chaosdroid

---

## 许可证

MIT License
