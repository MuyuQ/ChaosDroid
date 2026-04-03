@echo off
REM ChaosDroid Windows 部署脚本

setlocal enabledelayedexpansion

set CHAOSDROID_DIR=%CD%
set PYTHON_VERSION=3.11

echo ========================================
echo ChaosDroid Windows 部署脚本
echo ========================================

REM 1. 检查 Python
echo [1/5] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo Python 未安装，请先安装 Python 3.10+
    echo 下载地址：https://www.python.org/downloads/
    exit /b 1
)

REM 2. 创建虚拟环境
echo [2/5] 创建虚拟环境...
python -m venv .venv
call .venv\Scripts\activate.bat

REM 3. 安装 uv
echo [3/5] 安装 uv...
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

REM 4. 安装依赖
echo [4/5] 安装依赖...
uv pip install -e ".[dev]"

REM 5. 初始化数据库
echo [5/5] 初始化数据库...
python migrations/001_tracelens_integration.py

echo ========================================
echo 部署完成!
echo ========================================
echo.
echo 后续步骤:
echo 1. 复制 .env.example 为 .env
echo 2. 编辑 .env 修改配置 (API Key, CSRF Secret)
echo 3. 运行启动脚本：start.bat
echo 4. 访问 Web: http://localhost:8000
echo 5. 查看文档：README.md
echo.
