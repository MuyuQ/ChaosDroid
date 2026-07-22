# ChaosDroid

**Android 设备故障注入测试与诊断恢复验证平台**

> 主动制造异常，验证系统鲁棒性 —— 将人工构造故障环境的流程平台化

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构](#2-系统架构)
3. [核心特性](#3-核心特性)
4. [快速开始](#4-快速开始)
5. [部署指南](#5-部署指南)
6. [使用指南](#6-使用指南)
7. [TraceLens 诊断集成](#7-tracelens-诊断集成)
8. [故障注入类型](#8-故障注入类型)
9. [执行流程](#9-执行流程)
10. [API 参考](#10-api-参考)
11. [项目结构](#11-项目结构)
12. [配置参考](#12-配置参考)
13. [开发指南](#13-开发指南)

---

## 1. 项目概述

### 1.1 什么是 ChaosDroid？

ChaosDroid 是一个面向 Android 设备的**故障注入测试平台**，用于验证系统在异常条件下的**鲁棒性**和**恢复能力**。

通过集成 **TraceLens 诊断引擎**，ChaosDroid 不仅能注入故障，还能自动分析设备日志，识别潜在问题并提供诊断建议。

### 1.2 核心价值

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           传统测试 vs ChaosDroid                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   传统测试                      ChaosDroid                                  │
│   ┌──────────┐                 ┌──────────────────┐                        │
│   │ 输入正常 │                 │ 输入异常条件     │                        │
│   │ 数据     │                 │ (存储不足/断网/  │                        │
│   │          │                 │  低电量/高负载)  │                        │
│   └────┬─────┘                 └────────┬─────────┘                        │
│        │                                │                                   │
│        v                                v                                   │
│   ┌──────────┐                 ┌──────────────────┐                        │
│   │ 验证功能 │                 │ 验证系统如何     │                        │
│   │ 是否完成 │                 │ 失败、如何恢复   │                        │
│   └──────────┘                 └──────────────────┘                        │
│                                                                             │
│   目标：发现功能缺陷            目标：发现鲁棒性问题 + 自动诊断根因          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 适用场景

| 场景 | 描述 | 典型用例 |
|------|------|----------|
| **升级验证** | 验证 OTA 升级过程中断网、断电、存储不足时的表现 | OTA 升级中断恢复测试 |
| **稳定性测试** | 叠加资源压力后执行 monkey，验证系统是否恶化 | 72 小时稳定性压测 |
| **容错测试** | 验证应用在异常情况下的错误处理和恢复能力 | 网络抖动下的数据同步 |
| **恢复验证** | 验证系统故障后能否自动恢复，是否需要人工介入 | 系统崩溃后自愈测试 |
| **日志诊断** | 自动收集并分析故障日志，识别根因 | tombstone/ANR 日志分析 |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              ChaosDroid 整体架构                                │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                         表现层 (Presentation Layer)                      │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │   │
│  │  │   FastAPI       │  │   Typer CLI     │  │   Web UI        │         │   │
│  │  │   REST API      │  │   命令行工具    │  │   HTMX 页面     │         │   │
│  │  │   /api/*        │  │   chaosdroid    │  │   /             │         │   │
│  │  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘         │   │
│  └───────────┼────────────────────┼────────────────────┼──────────────────┘   │
│              │                    │                    │                       │
│              └────────────────────┼────────────────────┘                       │
│                                   │                                            │
│              ┌────────────────────▼────────────────────────────────────────┐  │
│              │                    业务层 (Business Layer)                    │  │
│              │  ┌───────────────────────────────────────────────────────┐  │  │
│              │  │              执行编排层 (Orchestration)                │  │  │
│              │  │   ScenarioOrchestratorService                          │  │  │
│              │  │   准备 → 注入 → 验证 → 恢复 → 日志收集 → 诊断          │  │  │
│              │  └───────────────────────────────────────────────────────┘  │  │
│              │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────┐│  │
│              │  │  Injector   │ │  Validator  │ │  Observer   │ │Recovery││  │
│              │  │  注入服务   │ │  验证服务   │ │  观测服务   │ │恢复服务││  │
│              │  └─────────────┘ └─────────────┘ └─────────────┘ └────────┘│  │
│              │  ┌─────────────────────────────────────────────────────────┐│  │
│              │  │           TraceLens 诊断集成层 (Diagnosis)              ││  │
│              │  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ││  │
│              │  │  │DiagnosisTrig │  │LogExportSvc  │  │EventDispatcher│  ││  │
│              │  │  │诊断触发器    │  │日志导出服务  │  │事件分发器     │  ││  │
│              │  │  └──────────────┘  └──────────────┘  └──────────────┘  ││  │
│              │  └─────────────────────────────────────────────────────────┘│  │
│              └─────────────────────────────────────────────────────────────┘  │
│                                   │                                            │
│              ┌────────────────────▼────────────────────────────────────────┐  │
│              │                 基础设施层 (Infrastructure)                   │  │
│              │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌─────────────┐  │  │
│              │  │ Scheduler │ │  Device   │ │   Lock    │ │  Database   │  │  │
│              │  │ 任务调度  │ │  设备池   │ │  设备锁   │ │  SQLite     │  │  │
│              │  └───────────┘ └───────────┘ └───────────┘ └─────────────┘  │  │
│              │  ┌───────────┐ ┌───────────┐ ┌───────────┐                  │  │
│              │  │   Mock    │ │   Real    │ │    ADB    │                  │  │
│              │  │ 模拟执行器│ │ 真实执行器│ │  驱动层   │                  │  │
│              │  └───────────┘ └───────────┘ └───────────┘                  │  │
│              └─────────────────────────────────────────────────────────────┘  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 TraceLens 诊断数据流

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          TraceLens 诊断数据流                                 │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────┐                                                          │
│   │  故障注入    │                                                          │
│   │  完成事件    │                                                          │
│   └──────┬───────┘                                                          │
│          │                                                                   │
│          v                                                                   │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                │
│   │ Scenario     │────>│ EventQueue   │────>│ Diagnosis    │                │
│   │ Orchestrator │     │ (事件队列)   │     │ Trigger      │                │
│   └──────────────┘     └──────────────┘     └──────┬───────┘                │
│                                                    │                        │
│                                                    v                        │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                │
│   │ Diagnosis    │<────│ LogExport    │<────│ Trigger      │                │
│   │ Result       │     │ Service      │     │ 触发日志导出 │                │
│   └──────┬───────┘     └──────────────┘     └──────────────┘                │
│          │                                                                   │
│          v                                                                   │
│   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                │
│   │ 分类诊断结果 │────>│ EventQueue   │────>│ Event        │                │
│   │ + 匹配规则   │     │ (诊断完成)   │     │ Dispatcher   │                │
│   └──────────────┘     └──────────────┘     └──────────────┘                │
│                                                  │                           │
│                                                  v                           │
│                                         ┌──────────────┐                     │
│                                         │ ChaosDroid   │                     │
│                                         │ 主数据库     │                     │
│                                         └──────────────┘                     │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 模块依赖关系

```
                                    ┌──────────┐
                                    │   main   │
                                    │  入口    │
                                    └────┬─────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
              ┌─────v─────┐      ┌───────v───────┐   ┌───────v───────┐
              │    CLI    │      │     API       │   │   Worker      │
              │  命令行   │      │   Web 服务    │   │  后台诊断轮询 │
              └─────┬─────┘      └───────┬───────┘   └───────┬───────┘
                    │                    │                   │
                    └────────────────────┼───────────────────┘
                                         │
                              ┌──────────▼──────────┐
                              │   Services 层       │
                              │  ┌───────────────┐  │
                              │  │ Orchestrator  │  │
                              │  └───────┬───────┘  │
                              │    ┌─────┴─────┐    │
                              │    v         v    │
                              │ ┌─────┐   ┌─────┐ │
                              │ │注入 │   │验证 │ │
                              │ └─────┘   └─────┘ │
                              └─────────┬─────────┘
                                        │
                              ┌─────────▼─────────┐
                              │   Executors       │
                              │  ┌─────┐ ┌─────┐  │
                              │  │Mock │ │Real │  │
                              │  └─────┘ └─────┘  │
                              └─────────┬─────────┘
                                        │
                              ┌─────────▼─────────┐
                              │   TraceLens       │
                              │  ┌─────┐ ┌─────┐  │
                              │  │导出 │ │诊断 │  │
                              │  └─────┘ └─────┘  │
                              └─────────┬─────────┘
                                        │
                                        v
                              ┌─────────────────┐
                              │   Android 设备   │
                              └─────────────────┘
```

---

## 3. 核心特性

### 3.1 故障注入能力

```
┌─────────────────────────────────────────────────────────────────┐
│                      6 种内置故障注入类型                        │
├──────────────────┬──────────────────────────────────────────────┤
│ storage_pressure │ 填充指定大小文件，模拟存储空间不足            │
│ low_battery      │ 模拟低电量场景，阻断任务执行                  │
│ network_jitter   │ 网络延迟、断网、超时等波动                    │
│ reboot_timeout   │ 重启超时模拟，验证设备上线能力                │
│ cpu_io_stress    │ CPU 和 I/O 压力注入，观察系统退化             │
│ monkey_stability │ Monkey 压测叠加资源压力                       │
└──────────────────┴──────────────────────────────────────────────┘
```

### 3.2 TraceLens 智能诊断

| 诊断类别 | 描述 | 检测内容 |
|---------|------|----------|
| **Bootloop** | 系统启动循环检测 | init 进程重启、watchdog 超时 |
| **System Crash** | 系统服务崩溃 | system_server、keymaster 等 |
| **HAL Crash** | 硬件抽象层崩溃 | vendor 分区服务崩溃 |
| **Kernel Panic** | 内核崩溃 | Kernel panic、Oops、BUG() |
| **Watchdog** | 看门狗超时 | SystemServerWatchdog、NativeWatchdog |
| **Security** | 安全模块异常 | SELinux、Keystore、Gatekeeper |
| **Audio** | 音频系统问题 | audioserver、hal.audio |
| **Camera** | 相机系统问题 | camera_service、hal.camera |
| **Connectivity** | 连接性问题 | wifi、bluetooth、netd |
| **Display** | 显示系统问题 | surfaceflinger、hwcomposer |
| **Power** | 电源管理问题 | powerhal、thermal、battery |
| **Performance** | 性能问题 | slow_op、binder 超时、内存压力 |
| **Stability** | 稳定性问题 | crash、ANR、tombstone |
| **Filesystem** | 文件系统问题 | f2fs、ext4、metadata 错误 |
| **Memory** | 内存问题 | OOM、ion、dmabuf 泄漏 |
| **Custom** | 自定义规则 | 用户自定义诊断规则 |

### 3.3 双模式执行

```
┌─────────────────────────────────────────────────────────────────┐
│                         执行模式选择                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Mock 模式                          Real 模式                  │
│   ┌─────────────────────┐          ┌─────────────────────┐     │
│   │ • 无需真实设备       │          │ • 连接真实 Android   │     │
│   │ • 快速开发和调试     │          │ • 执行真实注入操作   │     │
│   │ • CI/CD 自动化测试   │          │ • 验证实际效果       │     │
│   │ • 演示和培训         │          │ • 生产环境测试       │     │
│   │ • 自动模拟诊断结果   │          │ • 真实日志分析诊断   │     │
│   └─────────────────────┘          └─────────────────────┘     │
│                                                                 │
│   切换方式：--mode mock / --mode real                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.4 安全特性

| 特性 | 描述 |
|------|------|
| **路径验证** | 所有文件路径经过正则验证，阻止命令注入 |
| **设备锁** | 防止同一设备并发执行导致的冲突 |
| **API Key 认证** | 支持多 Key 配置，保护 API 端点 |
| **CSRF 保护** | Web 表单提交需要 CSRF Token |
| **风险等级** | 每个注入器有风险评级，高危险操作需确认 |

---

## 4. 快速开始

### 4.1 环境要求

- **Python**: 3.10+
- **操作系统**: Windows 10+/Linux (Ubuntu 20.04+)/macOS
- **可选**: Docker 20.10+ (用于容器化部署)

### 4.2 安装

```bash
# 1. 克隆仓库
git clone https://github.com/chaosdroid/chaosdroid.git
cd chaosdroid

# 2. 创建虚拟环境
python -m venv .venv

# 3. 激活虚拟环境
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 4. 安装 uv 包管理器
# Windows PowerShell:
irm https://astral.sh/uv/install.ps1 | iex
# Linux/macOS:
curl -LsSf https://astral.sh/uv/install.sh | sh

# 5. 安装项目依赖
uv pip install -e ".[dev]"
```

### 4.3 初始化

```bash
# 1. 复制环境配置
cp .env.example .env

# 2. 初始化数据库和目录结构
python migrations/001_tracelens_integration.py

# 输出:
# ✓ 数据库已初始化：./chaosdroid.db
# ✓ 创建产物目录：./artifacts
# ✓ 创建报告目录：./reports
# ✓ TraceLens 诊断表已创建
```

### 4.4 启动服务

```bash
# 启动 Web 服务
python start_server.py

# 访问:
# • Web UI: http://localhost:8000
# • API 文档：http://localhost:8000/docs
# • 健康检查：http://localhost:8000/health
```

### 4.5 执行第一个测试场景

```bash
# 步骤 1: 创建故障配置
python -m app.cli.main profile fault create \
  --name "存储压力测试" \
  --type storage_pressure \
  --params '{"pressure_mb": 500}' \
  --risk medium

# 步骤 2: 创建场景模板
python -m app.cli.main scenario create \
  --name "稳定性测试场景" \
  --fault-profile 1 \
  --validation-profile 1 \
  --recovery-profile 1 \
  --stage precheck \
  --mode mock

# 步骤 3: 执行场景
python -m app.cli.main run execute 1 --device test_device_001 --mode mock

# 步骤 4: 查看报告
python -m app.cli.main report show 1
```

---

## 5. 部署指南

### 5.1 部署方式总览

| 方式 | 适用场景 | 复杂度 | 推荐度 |
|------|---------|--------|--------|
| **Docker Compose** | 生产环境/容器化部署 | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Linux systemd** | 生产环境/Linux 服务器 | ⭐⭐ | ⭐⭐⭐⭐ |
| **Windows 手动** | 开发环境/Windows | ⭐ | ⭐⭐⭐ |
| **直接运行** | 快速测试/开发 | ⭐ | ⭐⭐ |

### 5.2 Docker Compose 部署

```bash
# 1. 复制配置文件
cp .env.example .env

# 2. 编辑环境配置（可选）
# 修改：CHAOSDROID_API_KEYS, CHAOSDROID_CSRF_SECRET

# 3. 构建并启动
docker-compose up -d --build

# 4. 查看状态
docker-compose ps
docker-compose logs -f

# 5. 执行数据库迁移
docker-compose exec chaosdroid python migrations/001_tracelens_integration.py

# 6. 访问服务
# http://localhost:8000

# 7. 停止服务
docker-compose down
```

### 5.3 Linux systemd 部署

```bash
# 1. 执行部署脚本
sudo ./deploy.sh

# 2. 编辑配置文件
sudo nano /opt/chaosdroid/.env
# 修改：CHAOSDROID_API_KEYS, CHAOSDROID_CSRF_SECRET

# 3. 启动服务
sudo systemctl start chaosdroid

# 4. 设置开机自启
sudo systemctl enable chaosdroid

# 5. 查看状态
sudo systemctl status chaosdroid
sudo journalctl -u chaosdroid -f
```

### 5.4 Windows 手动部署

```cmd
# 1. 执行部署脚本
deploy.bat

# 2. 复制配置文件
copy .env.example .env

# 3. 编辑配置
notepad .env

# 4. 启动服务
start.bat

# 5. 访问服务
# http://localhost:8000
```

### 5.5 生产环境配置

```bash
# 环境变量配置（推荐用于生产环境）
export CHAOSDROID_DATABASE_PATH=/var/lib/chaosdroid/chaosdroid.db
export CHAOSDROID_ARTIFACTS_DIR=/var/lib/chaosdroid/artifacts
export CHAOSDROID_REPORTS_DIR=/var/lib/chaosdroid/reports
export CHAOSDROID_API_KEYS='["your-production-api-key"]'
export CHAOSDROID_CSRF_SECRET="your-csrf-secret-change-this"
export CHAOSDROID_WEB_HOST=0.0.0.0
export CHAOSDROID_WEB_PORT=8000
```

详细部署文档请参考：[DEPLOYMENT.md](DEPLOYMENT.md)

---

## 6. 使用指南

### 6.1 命令行使用

#### 场景管理

```bash
# 列出所有场景
python -m app.cli.main scenario list

# 创建场景
python -m app.cli.main scenario create \
  --name "网络波动测试" \
  --fault-profile 2 \
  --stage runtime \
  --mode mock

# 查看场景详情
python -m app.cli.main scenario show 1

# 删除场景
python -m app.cli.main scenario delete 1
```

#### 执行管理

```bash
# 列出执行记录
python -m app.cli.main run list

# 执行场景
python -m app.cli.main run execute <scenario_id> --device <serial> --mode <mock|real>

# 查看执行状态
python -m app.cli.main run status <run_id>

# 取消执行
python -m app.cli.main run cancel <run_id>
```

#### 配置管理

```bash
# 创建故障配置
python -m app.cli.main profile fault create \
  --name "低电量测试" \
  --type low_battery \
  --params '{"target_level": 15}' \
  --risk low

# 创建验证配置
python -m app.cli.main profile validation create \
  --name "基础验证" \
  --checks boot_completed,battery_ok,storage_ok \
  --timeout 120

# 创建恢复配置
python -m app.cli.main profile recovery create \
  --name "基础恢复" \
  --actions cleanup_injection,reboot_if_needed \
  --timeout 300

# 列出配置
python -m app.cli.main profile list
```

#### 设备管理

```bash
# 列出设备
python -m app.cli.main device list

# 同步设备状态
python -m app.cli.main device sync

# 查看设备详情
python -m app.cli.main device show <serial>

# 重启设备
python -m app.cli.main device reboot <serial>
```

### 6.2 Python API 使用

#### 基本使用

```python
import asyncio
from app.executors.mock_executor import MockDeviceExecutor
from app.config.logging import setup_logging, get_logger

# 配置日志
logger = setup_logging(level="INFO")
log = get_logger("example")

async def main():
    # 创建 Mock 设备
    executor = MockDeviceExecutor("test_device_001")
    
    # 检查设备在线
    if await executor.is_online():
        log.info("设备在线")
        
        # 获取设备信息
        battery = await executor.get_battery_info()
        log.info(f"电量：{battery.level}%")
        
        storage = await executor.get_storage_info()
        log.info(f"可用存储：{storage.available / 1024 / 1024:.2f} MB")
        
        # 获取 logcat 日志
        logcat = await executor.get_logcat(lines=50)
        log.info(f"日志预览：{logcat[:200]}...")

asyncio.run(main())
```

#### 故障注入

```python
import asyncio
from datetime import datetime
from app.executors.mock_executor import MockDeviceExecutor
from app.injectors.storage_pressure import StoragePressureInjector
from app.injectors.base import InjectContext

async def inject_fault_example():
    # 创建执行器和注入器
    executor = MockDeviceExecutor("test_device_001")
    injector = StoragePressureInjector()
    
    # 创建注入上下文
    context = InjectContext(
        scenario_run_id=1,
        device_serial="test_device_001",
        executor=executor,
        fault_profile={"parameters": {"pressure_mb": 500}},
        artifacts_dir="./artifacts",
        started_at=datetime.utcnow(),
        inject_stage="precheck",
    )
    
    # 执行注入流程
    if await injector.prepare(context):
        print("准备成功")
        
        result = await injector.inject(context)
        print(f"注入结果：{result.success}")
        print(f"故障已注入：{result.fault_injected}")
        
        # 清理
        if result.cleanup_required:
            await injector.cleanup(context)
            print("清理完成")

asyncio.run(inject_fault_example())
```

### 6.3 REST API 使用

#### 创建并执行场景

```bash
# 1. 创建故障配置
curl -X POST "http://localhost:8000/api/profiles/fault" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "存储压力测试",
    "type": "storage_pressure",
    "parameters": {"pressure_mb": 500},
    "risk": "medium"
  }'

# 2. 创建场景
curl -X POST "http://localhost:8000/api/scenarios" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "稳定性测试",
    "fault_profile_id": 1,
    "validation_profile_id": 1,
    "recovery_profile_id": 1,
    "stage": "precheck",
    "mode": "mock"
  }'

# 3. 执行场景
curl -X POST "http://localhost:8000/api/runs/execute" \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": 1,
    "device_serial": "test_device_001",
    "mode": "mock"
  }'

# 4. 查询执行状态
curl "http://localhost:8000/api/runs/1/status"

# 5. 获取执行报告
curl "http://localhost:8000/api/runs/1/report"
```

### 6.4 Web UI 使用

ChaosDroid 提供基于 HTMX 的轻量级 Web UI：

1. **首页** (`/`): 查看系统概览和快速操作
2. **场景管理** (`/scenarios`): 创建、编辑、删除测试场景
3. **执行监控** (`/runs`): 实时查看执行状态和进度
4. **设备列表** (`/devices`): 管理已连接的设备
5. **报告查看** (`/reports`): 浏览和下载测试报告

---

## 7. TraceLens 诊断集成

### 7.1 诊断触发流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    TraceLens 诊断触发流程                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 故障注入完成                                                │
│     └─> 触发诊断事件到 EventQueue                               │
│                                                                 │
│  2. DiagnosisWorker 轮询 (每 5 秒)                               │
│     └─> 发现 pending 状态的诊断事件                              │
│                                                                 │
│  3. DiagnosisTrigger.run_diagnosis()                            │
│     ├─> 触发日志导出 (LogExportService)                         │
│     └─> 等待导出完成                                            │
│                                                                 │
│  4. TraceLens 诊断引擎                                          │
│     ├─> 读取导出的日志证据                                      │
│     ├─> 匹配诊断规则                                            │
│     └─> 返回 DiagnosticResult                                   │
│                                                                 │
│  5. 结果处理                                                    │
│     ├─> 更新 EventQueue 状态为 completed                        │
│     ├─> 分发事件到主数据库                                      │
│     └─> 诊断完成                                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 诊断配置

```bash
# .env 文件中的 TraceLens 配置

# TraceLens 诊断数据库
TRACELENS_DATABASE_URL=sqlite+aiosqlite:///./data/tracelens.db

# 原始证据存储路径
TRACELENS_ARTIFACTS_BASE_PATH=artifacts/raw

# 规则文件路径
TRACELENS_RULES_PATH=app/diagnosis/rules

# 相似度阈值 (0.0-1.0)
TRACELENS_SIMILARITY_THRESHOLD=0.3
```

### 7.3 诊断结果示例

```json
{
  "diagnosis_id": "dx_001",
  "device_serial": "test_device_001",
  "category": "system_crash",
  "confidence": 0.95,
  "summary": "System server crash detected",
  "matched_rules": [
    {
      "rule_id": "SYS_CRASH_001",
      "rule_name": "System Server Crash Detection",
      "confidence": 0.95,
      "evidence": [
        "android.server.systemserver: SystemServer exited with code 1",
        "FATAL EXCEPTION in system_server"
      ]
    }
  ],
  "severity": "high",
  "recommendations": [
    "Check system_server logs for root cause",
    "Verify recent system app updates",
    "Monitor for bootloop condition"
  ]
}
```

### 7.4 诊断触发 API

```bash
# 手动触发诊断（通过 API）
curl -X POST "http://localhost:8000/api/diagnosis/trigger" \
  -H "Content-Type: application/json" \
  -d '{
    "device_serial": "test_device_001",
    "event_type": "fault_injection_complete"
  }'

# 查询诊断结果
curl "http://localhost:8000/api/diagnosis/result/<diagnosis_id>"

# 列出所有诊断记录
curl "http://localhost:8000/api/diagnosis/list?device_serial=test_device_001"
```

详细 TraceLens 集成文档请参考：[docs/TRACLENS_INTEGRATION.md](docs/TRACLENS_INTEGRATION.md)

---

## 8. 故障注入类型

### 8.1 类型总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           故障注入类型矩阵                                  │
├──────────────────────┬──────────────┬──────────────┬───────────────────────┤
│ 故障类型             │ 风险等级     │ 注入阶段     │ 验证重点              │
├──────────────────────┼──────────────┼──────────────┼───────────────────────┤
│ storage_pressure     │ 中           │ precheck     │ 空间检查、清理恢复    │
│ low_battery          │ 低           │ precheck     │ 电量检查、充电恢复    │
│ network_jitter       │ 中           │ runtime      │ 重试机制、断点续传    │
│ reboot_timeout       │ 高           │ reboot_wait  │ 设备上线、状态恢复    │
│ cpu_io_stress        │ 中           │ runtime      │ 性能退化、系统稳定性  │
│ monkey_stability     │ 中           │ post_boot    │ crash/ANR 数量         │
└──────────────────────┴──────────────┴──────────────┴───────────────────────┘
```

### 8.2 配置示例

```bash
# 存储压力注入
python -m app.cli.main profile fault create \
  --name "存储压力 -1GB" \
  --type storage_pressure \
  --params '{"pressure_mb": 1000, "target_path": "/sdcard/chaosdroid"}' \
  --risk medium

# 低电量注入
python -m app.cli.main profile fault create \
  --name "低电量 -15%" \
  --type low_battery \
  --params '{"target_level": 15}' \
  --risk low

# 网络波动注入
python -m app.cli.main profile fault create \
  --name "网络延迟 -500ms" \
  --type network_jitter \
  --params '{"delay_ms": 500, "packet_loss": 0.1}' \
  --risk medium

# CPU/IO 压力注入
python -m app.cli.main profile fault create \
  --name "CPU/IO 压力" \
  --type cpu_io_stress \
  --params '{"duration_sec": 60, "io_path": "/sdcard/io_test"}' \
  --risk medium
```

---

## 9. 执行流程

### 9.1 状态流转图

```
                                    ┌──────────┐
                                    │  QUEUED  │
                                    │  排队中  │
                                    └────┬─────┘
                                         │
                              ┌──────────▼──────────┐
                              │    ALLOCATING       │
                              │   分配设备          │
                              └────┬────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
              ┌─────▼─────┐               ┌───────▼───────┐
              │ RESERVED  │               │   无设备      │
              │ 已分配    │               │   保持 QUEUED │
              └─────┬─────┘               └───────────────┘
                    │
              ┌─────▼─────┐
              │ PREPARING │
              │  准备中   │
              └─────┬─────┘
                    │
              ┌─────▼─────┐
              │ INJECTING │
              │  注入中   │
              └─────┬─────┘
                    │
              ┌─────▼─────┐
              │VALIDATING │
              │  验证中   │
              └─────┬─────┘
                    │
              ┌─────▼─────┐
              │RECOVERING │
              │  恢复中   │
              └─────┬─────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
  ┌─────▼─────┐ ┌───▼───┐ ┌────▼────┐
  │  PASSED   │ │FAILED │ │ PARTIAL │
  │   通过    │ │  失败 │ │  部分   │
  └───────────┘ └───────┘ └─────────┘
```

### 9.2 各阶段说明

| 阶段 | 状态 | 描述 | 超时时间 |
|------|------|------|----------|
| **排队** | QUEUED | 任务提交后进入排队状态 | - |
| **分配** | ALLOCATING | 调度器分配可用设备 | 30s |
| **预留** | RESERVED | 设备已分配，等待执行 | - |
| **准备** | PREPARING | 准备注入环境，采集初始状态 | 60s |
| **注入** | INJECTING | 执行故障注入 | 180s |
| **验证** | VALIDATING | 验证故障效果和系统状态 | 180s |
| **恢复** | RECOVERING | 清理注入效果，验证恢复 | 300s |
| **诊断** | DIAGNOSING | TraceLens 日志分析诊断 | 120s |
| **完成** | PASSED/FAILED/PARTIAL | 执行完成，生成报告 | - |

---

## 10. API 参考

### 10.1 场景管理 API

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/scenarios` | 列出所有场景 |
| POST | `/api/scenarios` | 创建新场景 |
| GET | `/api/scenarios/{id}` | 获取场景详情 |
| PUT | `/api/scenarios/{id}` | 更新场景 |
| DELETE | `/api/scenarios/{id}` | 删除场景 |
| POST | `/api/scenarios/{id}/execute` | 执行场景 |

### 10.2 执行管理 API

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/runs` | 列出所有执行记录 |
| POST | `/api/runs/execute` | 执行场景 |
| GET | `/api/runs/{id}` | 获取执行详情 |
| GET | `/api/runs/{id}/status` | 获取执行状态 |
| POST | `/api/runs/{id}/cancel` | 取消执行 |
| GET | `/api/runs/{id}/report` | 获取执行报告 |

### 10.3 配置管理 API

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/profiles` | 列出所有配置 |
| POST | `/api/profiles/fault` | 创建故障配置 |
| POST | `/api/profiles/validation` | 创建验证配置 |
| POST | `/api/profiles/recovery` | 创建恢复配置 |
| GET | `/api/profiles/{id}` | 获取配置详情 |
| DELETE | `/api/profiles/{id}` | 删除配置 |

### 10.4 设备管理 API

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/devices` | 列出所有设备 |
| POST | `/api/devices/sync` | 同步设备状态 |
| GET | `/api/devices/{serial}` | 获取设备详情 |
| POST | `/api/devices/{serial}/reboot` | 重启设备 |
| GET | `/api/devices/{serial}/logs` | 获取设备日志 |

### 10.5 诊断管理 API

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | `/api/diagnosis/trigger` | 触发诊断 |
| GET | `/api/diagnosis/result/{id}` | 获取诊断结果 |
| GET | `/api/diagnosis/list` | 列出诊断记录 |
| GET | `/api/diagnosis/stats` | 获取诊断统计 |

完整 API 文档请访问：http://localhost:8000/docs

---

## 11. 项目结构

```
chaosdroid/
├── app/
│   ├── api/                        # FastAPI Web 服务
│   │   ├── main.py                 # 应用入口
│   │   ├── middleware.py           # 认证中间件
│   │   └── routes/                 # API 路由
│   │       ├── scenarios.py        # 场景管理
│   │       ├── runs.py             # 执行管理
│   │       ├── profiles.py         # 配置管理
│   │       ├── devices.py          # 设备管理
│   │       ├── reports.py          # 报告管理
│   │       ├── diagnosis.py        # 诊断管理
│   │       └── web.py              # Web 页面
│   │
│   ├── cli/                        # Typer 命令行
│   │   ├── main.py                 # CLI 入口
│   │   └── ...                     # CLI 命令
│   │
│   ├── config/                     # 配置管理
│   │   ├── settings.py             # 环境配置
│   │   └── logging.py              # 日志配置
│   │
│   ├── diagnosis/                  # TraceLens 诊断集成
│   │   ├── rules/                  # 诊断规则
│   │   └── services/
│   │       └── trigger.py          # 诊断触发服务
│   │
│   ├── executors/                  # 执行器
│   │   ├── base.py                 # 执行器基类
│   │   ├── mock_executor.py        # Mock 执行器
│   │   └── real_executor.py        # 真实执行器
│   │
│   ├── injectors/                  # 故障注入器
│   │   ├── base.py                 # 注入器基类
│   │   └── ...                     # 各种注入器
│   │
│   ├── models/                     # 数据模型
│   │   ├── database.py             # 数据库配置
│   │   ├── scenario.py             # 场景模型
│   │   ├── profiles.py             # 配置模型
│   │   ├── device.py               # 设备模型
│   │   └── event_queue.py          # 事件队列模型
│   │
│   ├── services/                   # 业务服务层
│   │   ├── scenario_service.py     # 场景服务
│   │   ├── run_service.py          # 执行服务
│   │   ├── log_export_service.py   # 日志导出服务
│   │   └── event_dispatcher.py     # 事件分发器
│   │
│   ├── workers/                    # 后台任务
│   │   └── diagnosis_worker.py     # 诊断轮询 Worker
│   │
│   └── tests/                      # 测试
│       ├── conftest.py             # 测试配置
│       ├── factories.py            # 测试数据工厂
│       └── test_tracelens_integration.py
│
├── migrations/                     # 数据库迁移
│   └── 001_tracelens_integration.py
│
├── docs/                           # 文档
│   └── TRACLENS_INTEGRATION.md     # TraceLens 集成文档
│
├── deploy/                         # 部署配置
│   ├── Dockerfile                  # Docker 镜像
│   ├── docker-compose.yml          # Docker Compose
│   ├── chaosdroid.service          # systemd 服务
│   └── nginx.conf                  # Nginx 配置
│
├── pyproject.toml                  # 项目配置
├── start_server.py                 # 启动脚本
├── deploy.sh                       # Linux 部署脚本
├── deploy.bat                      # Windows 部署脚本
├── start.bat                       # Windows 启动脚本
└── verify_deploy.py                # 部署验证脚本
```

---

## 12. 配置参考

### 12.1 环境变量

```bash
# .env 文件示例

# ==================== 数据库配置 ====================
CHAOSDROID_DATABASE_PATH=./chaosdroid.db
TRACELENS_DATABASE_URL=sqlite+aiosqlite:///./data/tracelens.db

# ==================== 目录配置 ====================
CHAOSDROID_ARTIFACTS_DIR=./artifacts
CHAOSDROID_REPORTS_DIR=./reports
TRACELENS_ARTIFACTS_BASE_PATH=artifacts/raw

# ==================== 日志配置 ====================
CHAOSDROID_LOG_LEVEL=INFO
CHAOSDROID_LOG_FORMAT=text
CHAOSDROID_LOG_FILE=./logs/chaosdroid.log

# ==================== 超时配置 ====================
CHAOSDROID_PREPARE_TIMEOUT=60
CHAOSDROID_INJECT_TIMEOUT=180
CHAOSDROID_VALIDATE_TIMEOUT=180
CHAOSDROID_RECOVERY_TIMEOUT=300

# ==================== Web 服务配置 ====================
CHAOSDROID_WEB_HOST=0.0.0.0
CHAOSDROID_WEB_PORT=8000

# ==================== 安全配置 ====================
CHAOSDROID_API_KEYS='["chaosdroid-dev-key-2026"]'
CHAOSDROID_CSRF_SECRET="change-this-in-production"

# ==================== TraceLens 诊断配置 ====================
TRACELENS_RULES_PATH=app/diagnosis/rules
TRACELENS_SIMILARITY_THRESHOLD=0.3
```

### 12.2 日志配置

```python
from app.config.logging import setup_logging

# 方式 1: 默认配置
logger = setup_logging()

# 方式 2: 自定义配置
logger = setup_logging(
    level="DEBUG",
    log_format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
    date_format="%Y-%m-%d %H:%M:%S",
)

# 方式 3: 环境变量
# export CHAOSDROID_LOG_LEVEL=DEBUG
logger = setup_logging()  # 自动从环境变量加载
```

---

## 13. 开发指南

### 13.1 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest app/tests/test_tracelens_integration.py -v

# 运行覆盖率测试
pytest --cov=app --cov-report=html

# 查看覆盖率报告
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov\\index.html  # Windows
```

### 13.2 代码检查

```bash
# Ruff 检查
ruff check .

# Ruff 格式化
ruff format .

# MyPy 类型检查
mypy app/
```

### 13.3 扩展现有注入器

```python
from app.injectors.base import BaseInjector, FaultType, RiskLevel, InjectContext, InjectResult

class CustomInjector(BaseInjector):
    """自定义故障注入器"""

    fault_type = FaultType.custom
    risk_level = RiskLevel.medium

    async def prepare(self, context: InjectContext) -> bool:
        """准备注入环境"""
        executor = context.executor
        # 检查设备状态
        return await executor.is_online()

    async def inject(self, context: InjectContext) -> InjectResult:
        """执行故障注入"""
        params = context.fault_profile.get("parameters", {})
        # 执行注入逻辑

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
        # 清理逻辑
        return True

# 注册注入器
from app.injectors.base import register_injector
register_injector(CustomInjector())
```

### 13.4 贡献流程

```
1. Fork 本仓库
         │
         v
2. 创建功能分支 (git checkout -b feature/amazing-feature)
         │
         v
3. 提交更改 (git commit -m 'Add some amazing feature')
         │
         v
4. 推送到分支 (git push origin feature/amazing-feature)
         │
         v
5. 创建 Pull Request
         │
         v
6. 等待 Code Review
         │
         v
7. 合并到主分支
```

### 13.5 Git 提交规范

```
feat: 新功能
fix: 修复 bug
docs: 文档更新
style: 代码格式调整
refactor: 重构代码
test: 测试相关
chore: 构建/工具/配置相关
```

示例：
```bash
git commit -m "feat: 添加 CPU 压力注入器"
git commit -m "fix: 修复设备锁超时问题"
git commit -m "docs: 更新 API 使用示例"
```

---

## 许可证

MIT License

---

## 相关链接

- [API 文档](http://localhost:8000/docs)
- [快速部署指南](DEPLOY.md)
- [详细部署文档](DEPLOYMENT.md)
- [TraceLens 集成文档](docs/TRACLENS_INTEGRATION.md)
- [项目优化方案](docs/superpowers/specs/2026-04-02-chaosdroid-optimization-plan.md)

---
*最后更新: 2026-07-22*
