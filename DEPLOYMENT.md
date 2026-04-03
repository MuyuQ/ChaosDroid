# ChaosDroid 部署指南

**Android 设备故障注入测试与诊断恢复验证平台**

本文档提供 ChaosDroid 的完整部署说明，包括 TraceLens 诊断模块集成。

---

## 部署方式总览

| 方式 | 适用场景 | 推荐度 |
|------|---------|--------|
| Docker Compose | 生产环境/容器化部署 | ⭐⭐⭐⭐⭐ |
| Linux systemd | 生产环境/Linux 服务器 | ⭐⭐⭐⭐ |
| Windows 手动部署 | 开发环境/Windows | ⭐⭐⭐ |
| 直接运行 | 快速测试/开发 | ⭐⭐ |

---

## 方式一：Docker Compose（推荐）

### 前提条件

- Docker 20.10+
- Docker Compose 2.0+

### 部署步骤

```bash
# 1. 复制配置文件
cp .env.example .env
cp .env.production .env.production

# 2. 编辑生产配置
# 修改：CHAOSDROID_API_KEYS, CHAOSDROID_CSRF_SECRET

# 3. 构建并启动
docker-compose up -d --build

# 4. 查看状态
docker-compose ps
docker-compose logs -f

# 5. 执行数据库迁移
docker-compose exec chaosdroid python migrations/001_tracelens_integration.py

# 6. 停止服务
docker-compose down

# 7. 重启服务
docker-compose restart
```

### 访问地址

http://localhost:8000

---

## 方式二：Linux systemd 服务

### 前提条件

- Python 3.10+
- Ubuntu 20.04+/Debian 11+
- root 权限

### 部署步骤

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

# 6. 查看日志
sudo journalctl -u chaosdroid -f
```

### 访问地址

http://localhost:8000

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

## 相关文档

- 快速部署：[DEPLOY.md](DEPLOY.md)
- TraceLens 集成：[docs/TRACLENS_INTEGRATION.md](docs/TRACLENS_INTEGRATION.md)
- 使用指南：[README.md](README.md)
