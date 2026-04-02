# ChaosDroid

**Android 设备故障注入测试与恢复验证平台**

> 主动制造异常，验证系统鲁棒性 —— 将人工构造故障环境的流程平台化

---

## 目录

1. [项目概述](#1-项目概述)
2. [架构图](#2-架构图)
3. [核心特性](#3-核心特性)
4. [快速开始](#4-快速开始)
5. [使用指南](#5-使用指南)
6. [故障注入类型](#6-故障注入类型)
7. [执行流程](#7-执行流程)
8. [项目结构](#8-项目结构)
9. [配置参考](#9-配置参考)
10. [开发指南](#10-开发指南)

---

## 1. 项目概述

### 1.1 什么是 ChaosDroid？

ChaosDroid 是一个面向 Android 设备的**故障注入测试平台**，用于验证系统在异常条件下的**鲁棒性**和**恢复能力**。

传统测试验证"系统是否正常工作"，ChaosDroid 验证"系统在异常情况下能否正确失败并恢复"。

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
│   目标：发现功能缺陷            目标：发现鲁棒性问题                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 适用场景

| 场景 | 描述 |
|------|------|
| **升级验证** | 验证 OTA 升级过程中断网、断电、存储不足时的表现 |
| **稳定性测试** | 叠加资源压力后执行 monkey，验证系统是否恶化 |
| **容错测试** | 验证应用在异常情况下的错误处理和恢复能力 |
| **恢复验证** | 验证系统故障后能否自动恢复，是否需要人工介入 |

---

## 2. 架构图

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ChaosDroid 架构                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         表现层 (Presentation)                        │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │   │
│  │  │  FastAPI     │  │  Typer CLI   │  │  Web UI      │              │   │
│  │  │  REST API    │  │  命令行工具  │  │  HTMX 页面   │              │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      v                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                          业务层 (Business)                           │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │                    执行编排层                                 │   │   │
│  │  │   ScenarioOrchestratorService: 准备→注入→验证→恢复→收集      │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐       │   │
│  │  │  Injector  │ │ Validator  │ │  Observer  │ │  Recovery  │       │   │
│  │  │  注入服务  │ │  验证服务  │ │  观测服务  │ │  恢复服务  │       │   │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      v                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                       基础设施层 (Infrastructure)                    │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │   │
│  │  │  Scheduler  │ │   Device    │ │   Lock      │ │  Database   │   │   │
│  │  │  任务调度   │ │   设备池    │ │   设备锁    │ │   SQLite    │   │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘   │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                   │   │
│  │  │   Mock      │ │    Real     │ │    ADB      │                   │   │
│  │  │  模拟执行器 │ │  真实执行器 │ │   驱动      │                   │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 模块依赖关系

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
              │  命令行   │      │   Web 服务    │   │   后台调度    │
              └─────┬─────┘      └───────┬───────┘   └───────┬───────┘
                    │                    │                   │
                    └────────────────────┼───────────────────┘
                                         │
                              ┌──────────v──────────┐
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
                              ┌─────────v─────────┐
                              │   Executors       │
                              │  ┌─────┐ ┌─────┐  │
                              │  │Mock │ │Real │  │
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
│ 存储压力         │ 填充指定大小文件，模拟存储空间不足            │
│ low_battery      │ 模拟低电量场景，阻断任务执行                  │
│ network_jitter   │ 网络延迟、断网、超时等波动                    │
│ reboot_timeout   │ 重启超时模拟，验证设备上线能力                │
│ cpu_io_stress    │ CPU 和 I/O 压力注入，观察系统退化             │
│ monkey_stability │ Monkey 压测叠加资源压力                       │
└──────────────────┴──────────────────────────────────────────────┘
```

### 3.2 双模式执行

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
│   └─────────────────────┘          └─────────────────────┘     │
│                                                                 │
│   切换方式：--mode mock / --mode real                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 安全特性

| 特性 | 描述 |
|------|------|
| **路径验证** | 所有文件路径经过正则验证，阻止命令注入 |
| **设备锁** | 防止同一设备并发执行导致的冲突 |
| **API Key 认证** | 支持多 Key 配置，保护 API 端点 |
| **风险等级** | 每个注入器有风险评级，高危险操作需确认 |

---

## 4. 快速开始

### 4.1 安装

```bash
# 1. 克隆仓库
git clone https://github.com/chaosdroid/chaosdroid.git
cd chaosdroid

# 2. 创建虚拟环境
python -m venv .venv
source .venv/Scripts/activate  # Windows
# 或
source .venv/bin/activate      # macOS/Linux

# 3. 安装依赖
pip install -e .
```

### 4.2 初始化

```bash
# 初始化数据库和目录结构
chaosdroid init

# 输出:
# ✓ 数据库已初始化：./chaosdroid.db
# ✓ 创建产物目录：./artifacts
# ✓ 创建报告目录：./reports
```

### 4.3 启动服务

```bash
# 启动 Web 服务
chaosdroid serve

# 访问 http://localhost:8000 查看 Web UI
# 访问 http://localhost:8000/docs 查看 API 文档
```

### 4.4 执行第一个测试场景

```bash
# 步骤 1: 创建故障配置
chaosdroid profile fault create \
  --name "存储压力测试" \
  --type storage_pressure \
  --params '{"pressure_mb": 500}' \
  --risk medium

# 步骤 2: 创建场景模板
chaosdroid scenario create \
  --name "稳定性测试场景" \
  --fault-profile 1 \
  --validation-profile 1 \
  --recovery-profile 1 \
  --stage precheck \
  --mode mock

# 步骤 3: 执行场景
chaosdroid run execute 1 --device test_device_001 --mode mock

# 步骤 4: 查看报告
chaosdroid report show 1
```

---

## 5. 使用指南

### 5.1 命令行使用

#### 场景管理

```bash
# 列出所有场景
chaosdroid scenario list

# 创建场景
chaosdroid scenario create \
  --name "网络波动测试" \
  --fault-profile 2 \
  --stage runtime \
  --mode mock

# 查看场景详情
chaosdroid scenario show 1

# 删除场景
chaosdroid scenario delete 1
```

#### 执行管理

```bash
# 列出执行记录
chaosdroid run list

# 执行场景
chaosdroid run execute <scenario_id> --device <serial> --mode <mock|real>

# 查看执行状态
chaosdroid run status <run_id>

# 取消执行
chaosdroid run cancel <run_id>
```

#### 配置管理

```bash
# 创建故障配置
chaosdroid profile fault create \
  --name "低电量测试" \
  --type low_battery \
  --params '{"target_level": 15}' \
  --risk low

# 创建验证配置
chaosdroid profile validation create \
  --name "基础验证" \
  --checks boot_completed,battery_ok,storage_ok \
  --timeout 120

# 创建恢复配置
chaosdroid profile recovery create \
  --name "基础恢复" \
  --actions cleanup_injection,reboot_if_needed \
  --timeout 300

# 列出配置
chaosdroid profile list
```

#### 设备管理

```bash
# 列出设备
chaosdroid device list

# 同步设备状态
chaosdroid device sync

# 查看设备详情
chaosdroid device show <serial>

# 重启设备
chaosdroid device reboot <serial>
```

### 5.2 Python API 使用

#### 基本使用

```python
import asyncio
from chaosdroid.executors.mock_executor import MockDeviceExecutor
from chaosdroid.config.logging import setup_logging, get_logger

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
from chaosdroid.executors.mock_executor import MockDeviceExecutor
from chaosdroid.injectors.storage_pressure import StoragePressureInjector
from chaosdroid.injectors.base import InjectContext

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

#### 使用测试数据工厂

```python
from chaosdroid.tests.factories import (
    FaultProfileFactory,
    ValidationProfileFactory,
    ScenarioTemplateFactory,
    DeviceFactory,
    ScenarioFactory,
)

# 创建单个配置
fault_profile = FaultProfileFactory.create(
    name="网络延迟测试",
    fault_type="network_jitter",
    parameters={"delay_ms": 500, "packet_loss": 0.1},
)

# 创建设备
device = DeviceFactory.create(
    serial="Pixel7_001",
    model="Pixel 7",
    status="idle",
)

# 批量创建
devices = DeviceFactory.create_batch(5, status="idle")

# 创建完整场景
scenario = ScenarioFactory.create_full_scenario(
    name="稳定性测试",
    device_serial="test_device_001",
    mode="mock",
)
```

---

## 6. 故障注入类型

### 6.1 类型总览

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

### 6.2 配置示例

```bash
# 存储压力注入
chaosdroid profile fault create \
  --name "存储压力 -1GB" \
  --type storage_pressure \
  --params '{"pressure_mb": 1000, "target_path": "/sdcard/chaosdroid"}' \
  --risk medium

# 低电量注入
chaosdroid profile fault create \
  --name "低电量 -15%" \
  --type low_battery \
  --params '{"target_level": 15}' \
  --risk low

# 网络波动注入
chaosdroid profile fault create \
  --name "网络延迟 -500ms" \
  --type network_jitter \
  --params '{"delay_ms": 500, "packet_loss": 0.1}' \
  --risk medium

# CPU/IO 压力注入
chaosdroid profile fault create \
  --name "CPU/IO 压力" \
  --type cpu_io_stress \
  --params '{"duration_sec": 60, "io_path": "/sdcard/io_test"}' \
  --risk medium
```

---

## 7. 执行流程

### 7.1 状态流转图

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

### 7.2 各阶段说明

| 阶段 | 描述 | 超时时间 |
|------|------|----------|
| **QUEUED** | 任务提交后进入排队状态 | - |
| **ALLOCATING** | 调度器分配可用设备 | 30s |
| **RESERVED** | 设备已分配，等待执行 | - |
| **PREPARING** | 准备注入环境，采集初始状态 | 60s |
| **INJECTING** | 执行故障注入 | 180s |
| **VALIDATING** | 验证故障效果和系统状态 | 180s |
| **RECOVERING** | 清理注入效果，验证恢复 | 300s |

---

## 8. 项目结构

```
chaosdroid/
├── api/                        # FastAPI Web 服务
│   ├── main.py                 # 应用入口
│   ├── middleware.py           # 认证中间件
│   └── routes/                 # API 路由
│       ├── scenarios.py        # 场景管理
│       ├── runs.py             # 执行管理
│       ├── profiles.py         # 配置管理
│       ├── devices.py          # 设备管理
│       ├── pools.py            # 设备池管理
│       ├── reports.py          # 报告管理
│       └── web.py              # Web 页面
│
├── cli/                        # Typer 命令行
│   ├── main.py                 # CLI 入口
│   ├── init.py                 # 初始化命令
│   ├── scenario.py             # 场景命令
│   ├── run.py                  # 执行命令
│   ├── device.py               # 设备命令
│   ├── pool.py                 # 设备池命令
│   └── report.py               # 报告命令
│
├── config/                     # 配置管理
│   ├── settings.py             # 环境配置
│   └── logging.py              # 日志配置
│
├── executors/                  # 执行器
│   ├── base.py                 # 执行器基类
│   ├── mock_executor.py        # Mock 执行器
│   └── real_executor.py        # 真实执行器
│
├── injectors/                  # 故障注入器
│   ├── base.py                 # 注入器基类
│   ├── storage_pressure.py     # 存储压力注入
│   ├── low_battery.py          # 低电量注入
│   ├── network_jitter.py       # 网络波动注入
│   ├── reboot_timeout.py       # 重启超时注入
│   ├── cpu_io_stress.py        # CPU/IO 压力注入
│   └── monkey_stability.py     # Monkey 稳定性测试
│
├── models/                     # 数据模型
│   ├── base.py                 # 基础模型和枚举
│   ├── database.py             # 数据库配置
│   ├── scenario.py             # 场景模型
│   ├── profiles.py             # 配置模型
│   ├── device.py               # 设备模型
│   ├── device_pool.py          # 设备池模型
│   ├── device_lease.py         # 设备租约模型
│   └── event.py                # 事件模型
│
├── orchestrators/              # 执行编排
│   ├── execution.py            # 执行编排
│   └── state_machine.py        # 状态机
│
├── services/                   # 业务服务层
│   ├── scenario_service.py     # 场景服务
│   ├── run_service.py          # 执行服务
│   ├── execution_service.py    # 执行服务
│   ├── scenario_orchestrator_service.py  # 编排服务
│   ├── injector_dispatch_service.py      # 注入分发服务
│   ├── validation_service.py   # 验证服务
│   ├── observation_service.py  # 观测服务
│   ├── recovery_service.py     # 恢复服务
│   ├── report_service.py       # 报告服务
│   └── device_lock_manager.py  # 设备锁管理
│
├── scheduling/                 # 调度层
│   ├── scheduler.py            # 任务调度器
│   ├── pool_manager.py         # 设备池管理
│   ├── lease_manager.py        # 租约管理
│   ├── device_sync.py          # 设备同步
│   ├── quarantine.py           # 设备隔离
│   └── enums.py                # 调度枚举
│
├── tests/                      # 测试
│   ├── conftest.py             # 测试配置
│   ├── factories.py            # 测试数据工厂
│   ├── test_injectors.py       # 注入器测试
│   ├── test_services.py        # 服务层测试
│   └── test_integration.py     # 集成测试
│
└── templates/                  # 报告模板
    └── reports/
        ├── markdown.jinja2     # Markdown 模板
        └── html.jinja2         # HTML 模板
```

---

## 9. 配置参考

### 9.1 环境变量

```bash
# .env 文件示例

# ==================== 数据库配置 ====================
CHAOSDROID_DATABASE_PATH=./chaosdroid.db

# ==================== 目录配置 ====================
CHAOSDROID_ARTIFACTS_DIR=./artifacts
CHAOSDROID_REPORTS_DIR=./reports

# ==================== 日志配置 ====================
CHAOSDROID_LOG_LEVEL=INFO
CHAOSDROID_LOG_FORMAT=text
CHAOSDROID_LOG_FORMAT_STRING="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
CHAOSDROID_LOG_FILE=./logs/chaosdroid.log
CHAOSDROID_LOG_BACKUP_COUNT=30

# ==================== 超时配置 ====================
CHAOSDROID_PREPARE_TIMEOUT=60
CHAOSDROID_INJECT_TIMEOUT=180
CHAOSDROID_VALIDATE_TIMEOUT=180
CHAOSDROID_RECOVERY_TIMEOUT=300

# ==================== Web 服务配置 ====================
CHAOSDROID_WEB_HOST=0.0.0.0
CHAOSDROID_WEB_PORT=8000

# ==================== 安全配置 ====================
CHAOSDROID_API_KEYS='["my-secret-key-123", "another-key-456"]'
CHAOSDROID_AUTH_EXCLUDE_PATHS='["/health", "/docs", "/openapi.json"]'
```

### 9.2 日志配置

```python
from chaosdroid.config.logging import setup_logging

# 方式 1: 默认配置
logger = setup_logging()

# 方式 2: 自定义配置
logger = setup_logging(
    level="DEBUG",
    log_format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
    date_format="%Y-%m-%d %H:%M:%S",
)

# 方式 3: 环境变量
# export CHAOSDROID_LOG_FORMAT_STRING="..."
# export CHAOSDROID_LOG_FILE="/var/log/chaosdroid/app.log"
logger = setup_logging()  # 自动从环境变量加载
```

---

## 10. 开发指南

### 10.1 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest chaosdroid/tests/test_injectors.py -v

# 运行覆盖率测试
pytest --cov=chaosdroid --cov-report=html

# 查看覆盖率报告
open htmlcov/index.html
```

### 10.2 代码检查

```bash
# Ruff 检查
ruff check .

# Ruff 格式化
ruff format .

# MyPy 类型检查
mypy chaosdroid/
```

### 10.3 扩展注入器

```python
from chaosdroid.injectors.base import BaseInjector, FaultType, RiskLevel, InjectContext, InjectResult

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
from chaosdroid.injectors.base import register_injector
register_injector(CustomInjector())
```

### 10.4 贡献流程

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

---

## 许可证

MIT License

---

## 相关链接

- [API 文档](http://localhost:8000/docs)
- [项目规划](docs/chaosdroid_project_plan.md)
- [技术报告](docs/chaosdroid_technical_report.md)
- [优化方案](docs/superpowers/specs/2026-04-02-chaosdroid-optimization-plan.md)
