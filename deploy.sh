#!/bin/bash
# ChaosDroid 部署脚本 (Linux)

set -e

CHAOSDROID_DIR="/opt/chaosdroid"
DATA_DIR="/var/lib/chaosdroid"
LOG_DIR="/var/log/chaosdroid"
PYTHON_VERSION="3.11"

echo "========================================"
echo "ChaosDroid 部署脚本"
echo "========================================"

# 检查是否以 root 运行
if [ "$EUID" -ne 0 ]; then
    echo "请以 root 用户运行此脚本 (sudo ./deploy.sh)"
    exit 1
fi

# 1. 创建目录
echo "[1/6] 创建目录..."
mkdir -p "$CHAOSDROID_DIR"
mkdir -p "$DATA_DIR"/{artifacts,reports,data,logs}
mkdir -p "$LOG_DIR"

# 2. 安装 Python
echo "[2/6] 检查 Python 环境..."
if ! command -v python3 &> /dev/null; then
    echo "安装 Python $PYTHON_VERSION..."
    apt update && apt install -y python$PYTHON_VERSION python3-pip python3-venv
fi

# 3. 复制项目文件
echo "[3/6] 部署项目文件..."
cp -r app "$CHAOSDROID_DIR/"
cp pyproject.toml "$CHAOSDROID_DIR/"
cp start_server.py "$CHAOSDROID_DIR/"
cp migrations "$CHAOSDROID_DIR/" -r

# 4. 创建虚拟环境并安装依赖
echo "[4/6] 创建虚拟环境..."
cd "$CHAOSDROID_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"

# 5. 初始化数据库
echo "[5/6] 初始化数据库..."
python migrations/001_tracelens_integration.py

# 6. 配置文件
echo "[6/6] 生成配置文件..."
if [ ! -f "$CHAOSDROID_DIR/.env" ]; then
    cp .env.production "$CHAOSDROID_DIR/.env"
    echo "请编辑 $CHAOSDROID_DIR/.env 修改以下配置:"
    echo "  - CHAOSDROID_API_KEYS"
    echo "  - CHAOSDROID_CSRF_SECRET"
fi

# 7. 安装 systemd 服务
echo "安装 systemd 服务..."
cp deploy/chaosdroid.service /etc/systemd/system/
systemctl daemon-reload

echo "========================================"
echo "部署完成!"
echo "========================================"
echo ""
echo "后续步骤:"
echo "1. 编辑配置文件：nano $CHAOSDROID_DIR/.env"
echo "2. 启动服务：systemctl start chaosdroid"
echo "3. 设置开机自启：systemctl enable chaosdroid"
echo "4. 查看状态：systemctl status chaosdroid"
echo "5. 访问 Web: http://localhost:8000"
echo "6. 查看文档：$CHAOSDROID_DIR/README.md"
