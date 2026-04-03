# ChaosDroid 部署指南

## 快速部署

### 1. 环境准备

```bash
# 确保 Python 3.10+ 已安装
python --version

# 进入项目目录
cd E:\git_repositories\ChaosDroid
```

### 2. 安装依赖

```bash
# 创建虚拟环境（如果尚未创建）
python -m venv .venv

# 激活虚拟环境（Windows）
.venv\Scripts\activate

# 安装依赖
pip install -e .
```

### 3. 配置文件

```bash
# 复制环境配置模板
cp .env.example .env

# 编辑 .env 文件，修改以下配置：
# - CHAOSDROID_API_KEYS: 设置你的 API Key
# - CHAOSDROID_CSRF_SECRET: 设置 CSRF 密钥（生产环境必须修改）
```

### 4. 创建必要目录

```bash
# 脚本会自动创建以下目录：
# - logs/         日志文件
# - data/         诊断数据
# - artifacts/    执行产物
# - reports/      报告输出
```

### 5. 启动服务器

```bash
# 方式 1: 使用启动脚本（推荐）
.venv\Scripts\python.exe start_server.py

# 方式 2: 使用 uvicorn 直接启动
.venv\Scripts\uvicorn.exe app.api.main:app --host 0.0.0.0 --port 8000

# 方式 3: 使用 CLI 命令（安装后）
chaosdroid serve
```

### 6. 访问应用

- **Web UI**: http://localhost:8000/
- **API 文档**: http://localhost:8000/docs
- **诊断界面**: http://localhost:8000/diagnosis

---

## 生产环境部署

### 系统服务配置（Windows）

使用 NSSM 或 Task Scheduler 将 ChaosDroid 注册为系统服务。

### 环境变量

生产环境建议使用环境变量而非 `.env` 文件：

```bash
# 数据库
export CHAOSDROID_DATABASE_PATH=/var/lib/chaosdroid/chaosdroid.db
export TRACELENS_DATABASE_URL=sqlite+aiosqlite:///./data/tracelens.db

# 目录
export CHAOSDROID_ARTIFACTS_DIR=/var/lib/chaosdroid/artifacts
export CHAOSDROID_REPORTS_DIR=/var/lib/chaosdroid/reports

# 安全
export CHAOSDROID_API_KEYS='["your-production-api-key"]'
export CHAOSDROID_CSRF_SECRET="your-csrf-secret-change-this"

# Web 服务
export CHAOSDROID_WEB_HOST=0.0.0.0
export CHAOSDROID_WEB_PORT=8000
```

### 反向代理（Nginx）

```nginx
server {
    listen 80;
    server_name chaosdroid.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

---

## 配置说明

### 主应用配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `CHAOSDROID_DATABASE_PATH` | 数据库路径 | `./chaosdroid.db` |
| `CHAOSDROID_ARTIFACTS_DIR` | 产物目录 | `./artifacts` |
| `CHAOSDROID_REPORTS_DIR` | 报告目录 | `./reports` |
| `CHAOSDROID_LOG_LEVEL` | 日志级别 | `INFO` |
| `CHAOSDROID_WEB_HOST` | 监听主机 | `0.0.0.0` |
| `CHAOSDROID_WEB_PORT` | 监听端口 | `8000` |
| `CHAOSDROID_API_KEYS` | API Key 列表 | `[]` |
| `CHAOSDROID_CSRF_SECRET` | CSRF 密钥 | （默认值） |

### TraceLens 诊断配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `TRACELENS_DATABASE_URL` | 诊断数据库 URL | `sqlite+aiosqlite:///./data/tracelens.db` |
| `TRACELENS_ARTIFACTS_BASE_PATH` | 原始证据存储路径 | `artifacts/raw` |
| `TRACELENS_RULES_PATH` | 规则文件路径 | `app/diagnosis/rules` |
| `TRACELENS_SIMILARITY_THRESHOLD` | 相似度阈值 | `0.3` |

---

## 健康检查

```bash
# 健康检查端点
curl http://localhost:8000/health

# 预期响应
{"status": "healthy"}
```

---

## 日志查看

```bash
# 查看实时日志
tail -f logs/chaosdroid.log

# 查看错误日志
grep ERROR logs/chaosdroid.log
```

---

## 故障排除

### 端口被占用

```bash
# Windows: 查找占用端口的进程
netstat -ano | findstr :8000

# 终止进程
taskkill /PID <PID> /F
```

### 数据库锁定

如果遇到数据库锁定错误：
1. 停止服务器
2. 检查是否有残留进程
3. 确保没有其他进程访问数据库

### 导入错误

```bash
# 重新安装依赖
pip install -e . --force-reinstall
```

---

## 版本信息

- **ChaosDroid**: 0.1.0
- **Python**: 3.10+
- **FastAPI**: 0.100.0+
