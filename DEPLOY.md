# ChaosDroid 快速部署

## 5 分钟快速启动

### Windows

```cmd
REM 1. 部署
deploy.bat

REM 2. 配置
copy .env.example .env
notepad .env

REM 3. 启动
python start_server.py
```

### Linux

```bash
# 1. 部署
sudo ./deploy.sh

# 2. 配置
sudo nano /opt/chaosdroid/.env

# 3. 启动
sudo systemctl start chaosdroid
```

### Docker

```bash
# 1. 配置
cp .env.example .env

# 2. 启动
docker-compose up -d

# 3. 迁移
docker-compose exec chaosdroid python migrations/001_tracelens_integration.py
```

## 访问

- **Web UI**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

## 默认配置

| 项目 | 值 |
|------|-----|
| 端口 | 8000 |
| 数据库 | ./chaosdroid.db |
| API Key | chaosdroid-dev-key-2026 |

⚠️ **生产环境必须修改 API Key 和 CSRF Secret！**

## 相关文档

- 详细部署文档：[DEPLOYMENT.md](DEPLOYMENT.md)
- TraceLens 集成：[docs/TRACLENS_INTEGRATION.md](docs/TRACLENS_INTEGRATION.md)
- 完整使用指南：[README.md](README.md)
