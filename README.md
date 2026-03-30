# ChaosDroid

**Android 故障注入测试与恢复验证平台**

ChaosDroid 是一个用于 Android 设备的故障注入测试框架，支持多种故障类型的注入、执行验证、恢复操作和结果判定。适用于 Android 应用的稳定性测试、容错能力验证和恢复机制评估。

## 特性

- **多种故障注入类型**：存储压力、低电量、网络波动、重启超时、CPU/I/O压力、Monkey稳定性测试
- **灵活的注入阶段**：支持预检查、运行时、后台等多个注入阶段
- **双执行模式**：支持真实设备模式和Mock模拟模式，便于测试和开发
- **完整的执行流程**：准备→注入→验证→恢复→收集，每步都有详细记录
- **自动恢复验证**：注入后自动验证设备状态并执行恢复操作
- **设备锁管理**：防止同一设备并发执行导致的冲突
- **详细报告生成**：支持 Markdown 和 HTML 格式的测试报告
- **Web界面**：提供 RESTful API 和基于 HTMX 的 Web UI
- **命令行工具**：完整的 CLI 支持，便于自动化集成

## 安装

### 从源码安装

```bash
# 克隆仓库
git clone https://github.com/chaosdroid/chaosdroid.git
cd chaosdroid

# 使用 uv 安装（推荐）
uv sync

# 或使用 pip
pip install -e .
```

### 依赖要求

- Python >= 3.10
- SQLite（默认数据库）
- ADB（仅真实设备模式需要）

## 快速开始

### 1. 初始化

```bash
# 初始化数据库和目录结构
chaosdroid init

# 指定自定义路径
chaosdroid init --db /path/to/chaosdroid.db --artifacts ./artifacts --reports ./reports
```

### 2. 启动服务

```bash
# 启动 Web 服务
chaosdroid serve

# 指定端口和主机
chaosdroid serve --host 0.0.0.0 --port 8080

# 开启调试模式
chaosdroid serve --debug
```

### 3. 创建测试场景

```bash
# 创建故障配置
chaosdroid profile fault create \
  --name "存储压力测试" \
  --type storage_pressure \
  --params '{"pressure_mb": 500}' \
  --risk medium

# 创建场景模板
chaosdroid scenario create \
  --name "稳定性测试场景" \
  --fault-profile 1 \
  --validation-profile 1 \
  --recovery-profile 1 \
  --stage precheck \
  --mode mock
```

### 4. 执行测试

```bash
# 列出可用场景
chaosdroid scenario list

# 执行场景（Mock模式）
chaosdroid run execute 1 --device test_device_001 --mode mock

# 执行场景（真实设备）
chaosdroid run execute 1 --device ABC123456 --mode real

# 查看执行状态
chaosdroid run status 1
```

### 5. 查看报告

```bash
# 列出报告
chaosdroid report list

# 查看报告摘要
chaosdroid report show 1

# 导出报告
chaosdroid report export 1 --format html --output ./report.html
```

## 故障注入类型

| 类型 | 描述 | 风险等级 |
|------|------|----------|
| `storage_pressure` | 存储空间压力注入，填充指定大小的文件 | 中 |
| `low_battery` | 模拟低电量场景 | 低 |
| `network_jitter` | 网络波动注入（延迟/断网/超时） | 中 |
| `reboot_timeout` | 重启超时模拟 | 高 |
| `cpu_io_stress` | CPU和I/O压力注入 | 中 |
| `monkey_stability` | Monkey稳定性测试 | 中 |

## 注入阶段

| 阶段 | 描述 |
|------|------|
| `precheck` | 预检查阶段，应用启动前注入 |
| `runtime` | 运行时阶段，应用运行中注入 |
| `background` | 后台阶段，应用在后台时注入 |

## 项目结构

```
chaosdroid/
├── api/                    # FastAPI 路由和 Web UI
│   ├── routes/             # API 端点定义
│   └── templates/          # Jinja2 HTML 模板
├── cli/                    # Typer 命令行工具
├── config/                 # 配置管理和日志设置
├── executors/              # 设备执行器（Mock/Real）
├── injectors/              # 故障注入器实现
├── models/                 # SQLAlchemy 数据模型
├── observers/              # 观测数据收集器
├── orchestrators/          # 执行流程编排
├── services/               # 业务逻辑服务层
└── tests/                  # 测试用例
```

## API 文档

启动服务后访问：
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### 主要 API 端点

```
# 场景管理
GET    /api/scenarios           # 列出场景
POST   /api/scenarios           # 创建场景
GET    /api/scenarios/{id}      # 获取场景详情
PUT    /api/scenarios/{id}      # 更新场景
DELETE /api/scenarios/{id}      # 删除场景

# 执行管理
GET    /api/runs                # 列出执行记录
POST   /api/runs                # 创建执行记录
POST   /api/runs/{id}/execute   # 执行场景
POST   /api/runs/{id}/cancel    # 取消执行

# 配置管理
GET    /api/profiles/fault      # 故障配置
GET    /api/profiles/validation # 验证配置
GET    /api/profiles/recovery   # 恢复配置

# 设备管理
GET    /api/devices             # 列出设备
GET    /api/devices/{serial}    # 设备详情
POST   /api/devices/{serial}/reboot  # 重启设备

# 报告
GET    /api/reports             # 列出报告
GET    /api/reports/{id}        # 报告详情
GET    /api/reports/{id}/html   # HTML 报告
```

## 配置

### 环境变量

```bash
# 数据库配置
CHAOSDROID_DATABASE_PATH=./chaosdroid.db

# 目录配置
CHAOSDROID_ARTIFACTS_DIR=./artifacts
CHAOSDROID_REPORTS_DIR=./reports

# 日志配置
CHAOSDROID_LOG_LEVEL=INFO
CHAOSDROID_LOG_FORMAT=text  # text 或 json
CHAOSDROID_LOG_FORMAT_STRING="%(asctime)s | %(levelname)s | %(name)s | %(message)s"

# 超时配置（秒）
CHAOSDROID_PREPARE_TIMEOUT=60
CHAOSDROID_INJECT_TIMEOUT=180
CHAOSDROID_VALIDATE_TIMEOUT=180
CHAOSDROID_RECOVERY_TIMEOUT=300
```

## 开发

### 运行测试

```bash
# 运行所有测试
uv run pytest

# 运行特定测试文件
uv run pytest chaosdroid/tests/test_injectors.py -v

# 生成覆盖率报告
uv run pytest --cov=chaosdroid --cov-report=html
```

### 代码检查

```bash
# Ruff 检查
uv run ruff check .

# Ruff 格式化
uv run ruff format .

# MyPy 类型检查
uv run mypy chaosdroid/
```

## 扩展注入器

创建自定义注入器：

```python
from chaosdroid.injectors.base import BaseInjector, FaultType, RiskLevel, InjectContext, InjectResult

class CustomInjector(BaseInjector):
    """自定义故障注入器"""

    fault_type = FaultType.custom
    risk_level = RiskLevel.medium

    async def prepare(self, context: InjectContext) -> bool:
        """准备注入环境"""
        executor = context.executor
        # 检查设备状态...
        return await executor.is_online()

    async def inject(self, context: InjectContext) -> InjectResult:
        """执行故障注入"""
        params = context.fault_profile.get("parameters", {})
        # 执行注入逻辑...

        return InjectResult(
            success=True,
            fault_type=self.fault_type,
            fault_injected=True,
            fault_observed=True,
            message="注入成功",
            details={},
            cleanup_required=True
        )

    async def cleanup(self, context: InjectContext) -> bool:
        """清理注入效果"""
        # 清理逻辑...
        return True

# 注册注入器
from chaosdroid.injectors.base import register_injector
register_injector(CustomInjector())
```

## 执行流程

```
┌─────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
│ Queued  │───>│ Preparing │───>│ Injecting │───>│ Validating│───>│ Recovering│
└─────────┘    └───────────┘    └───────────┘    └───────────┘    └───────────┘
                    │                │                │                │
                    v                v                v                v
               ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
               │ Failed  │     │ Failed  │     │ Failed  │     │ Partial │
               └─────────┘     └─────────┘     └─────────┘     └─────────┘
                                                                    │
                                                                    v
                                                              ┌──────────┐
                                                              │ Passed   │
                                                              │ Failed   │
                                                              │ Partial  │
                                                              └──────────┘
```

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request