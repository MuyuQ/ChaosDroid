FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 复制项目文件
COPY pyproject.toml README.md DEPLOY.md DEPLOYMENT.md ./
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY docs/ ./docs/
COPY start_server.py ./
COPY docker-compose.yml ./

# 安装依赖
RUN uv pip install --system --no-cache -e ".[dev]"

# 创建必要的目录
RUN mkdir -p /var/lib/chaosdroid/{artifacts,reports,data,logs} \
    && mkdir -p /var/log/chaosdroid

# 设置环境变量
ENV CHAOSDROID_DATABASE_PATH=/var/lib/chaosdroid/chaosdroid.db
ENV CHAOSDROID_ARTIFACTS_DIR=/var/lib/chaosdroid/artifacts
ENV CHAOSDROID_REPORTS_DIR=/var/lib/chaosdroid/reports
ENV CHAOSDROID_DATA_DIR=/var/lib/chaosdroid/data
ENV CHAOSDROID_LOG_FILE=/var/log/chaosdroid/chaosdroid.log
ENV CHAOSDROID_WEB_HOST=0.0.0.0
ENV CHAOSDROID_WEB_PORT=8000

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 启动命令
CMD ["python", "start_server.py"]
