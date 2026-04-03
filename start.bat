@echo off
REM ChaosDroid Windows 启动脚本
REM 用法：直接双击运行，或在命令行中执行

echo ========================================
echo ChaosDroid 服务器
echo ========================================

REM 检查虚拟环境
if not exist ".venv\Scripts\activate.bat" (
    echo 错误：虚拟环境不存在，请先运行 deploy.bat
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo 启动服务器...
echo 访问地址：http://localhost:8000
echo API 文档：http://localhost:8000/docs
echo ========================================

python start_server.py
