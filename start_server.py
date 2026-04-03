"""ChaosDroid 服务器启动脚本 - 生产环境。"""
import os
import sys
import logging
from pathlib import Path

# 确保日志目录存在
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# 确保数据目录存在
data_dir = Path("data")
data_dir.mkdir(exist_ok=True)

# 确保产物目录存在
artifacts_dir = Path("artifacts")
artifacts_dir.mkdir(exist_ok=True)

# 确保报告目录存在
reports_dir = Path("reports")
reports_dir.mkdir(exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
    handlers=[
        logging.FileHandler("logs/chaosdroid.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    import uvicorn
    from app.api.main import app

    host = os.getenv("CHAOSDROID_WEB_HOST", "0.0.0.0")
    port = int(os.getenv("CHAOSDROID_WEB_PORT", "8000"))

    logger.info(f"启动 ChaosDroid 服务器：http://{host}:{port}")
    logger.info(f"API 文档：http://{host}:{port}/docs")
    logger.info(f"诊断界面：http://{host}:{port}/diagnosis")

    uvicorn.run(app, host=host, port=port, log_level="info")
