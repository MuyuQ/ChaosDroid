"""ChaosDroid 日志配置模块。

提供统一的日志配置，支持：
- 控制台输出
- 文件输出（按日期滚动）
- 可配置的日志级别
"""

import logging
import sys
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

from .settings import get_settings


# 日志格式
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 日志目录
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "chaosdroid.log"

# 日志级别映射
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def setup_logging(
    level: Optional[str] = None,
    log_file: Optional[Path] = None,
    enable_console: bool = True,
    enable_file: bool = True,
) -> logging.Logger:
    """配置应用日志。

    Args:
        level: 日志级别，如果未指定则从配置读取
        log_file: 日志文件路径，如果未指定则使用默认路径
        enable_console: 是否启用控制台输出
        enable_file: 是否启用文件输出

    Returns:
        logging.Logger: 配置好的根日志器
    """
    # 获取配置
    settings = get_settings()
    log_level = level or settings.log_level
    log_level = log_level.upper()

    # 验证日志级别
    if log_level not in LOG_LEVELS:
        raise ValueError(
            f"无效的日志级别: {log_level}，有效值为: {', '.join(LOG_LEVELS.keys())}"
        )

    # 确保日志目录存在
    if enable_file:
        if log_file is None:
            log_file = LOG_FILE
        log_file.parent.mkdir(parents=True, exist_ok=True)

    # 获取根日志器
    root_logger = logging.getLogger("chaosdroid")
    root_logger.setLevel(LOG_LEVELS[log_level])

    # 清除已有的处理器，避免重复添加
    root_logger.handlers.clear()

    # 创建格式器
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # 添加控制台处理器
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(LOG_LEVELS[log_level])
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # 添加文件处理器（按日期滚动）
    if enable_file and log_file is not None:
        file_handler = TimedRotatingFileHandler(
            filename=str(log_file),
            when="midnight",  # 每天午夜滚动
            interval=1,  # 间隔1天
            backupCount=30,  # 保留30天的日志
            encoding="utf-8",
        )
        file_handler.setLevel(LOG_LEVELS[log_level])
        file_handler.setFormatter(formatter)
        # 设置滚动后的文件名格式
        file_handler.suffix = "%Y-%m-%d"
        root_logger.addHandler(file_handler)

    # 防止日志向上传播到根日志器
    root_logger.propagate = False

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志器。

    Args:
        name: 日志器名称，通常使用模块名

    Returns:
        logging.Logger: 日志器实例

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("这是一条日志")
    """
    # 确保名称以 chaosdroid 开头
    if not name.startswith("chaosdroid"):
        name = f"chaosdroid.{name}"

    return logging.getLogger(name)


def log_startup_info(logger: logging.Logger) -> None:
    """记录启动信息。

    Args:
        logger: 日志器实例
    """
    settings = get_settings()
    logger.info("=" * 60)
    logger.info("ChaosDroid 启动")
    logger.info("=" * 60)
    logger.info("配置信息:")
    logger.info(f"  数据库路径: {settings.database_path}")
    logger.info(f"  产物目录: {settings.artifacts_dir}")
    logger.info(f"  报告目录: {settings.reports_dir}")
    logger.info(f"  ADB 路径: {settings.adb_path}")
    logger.info(f"  默认超时: {settings.default_timeout} 秒")
    logger.info(f"  Web 端口: {settings.web_port}")
    logger.info(f"  日志级别: {settings.log_level}")
    logger.info(f"  危险操作确认: {settings.dangerous_operations_require_confirm}")
    logger.info("=" * 60)


class LogLevelContext:
    """临时更改日志级别的上下文管理器。

    用于在特定代码块中临时调整日志级别。

    Example:
        >>> with LogLevelContext("DEBUG"):
        ...     logger.debug("这条日志会被输出")
        >>> logger.debug("这条日志不会输出（如果默认级别是 INFO）")
    """

    def __init__(self, level: str):
        """初始化上下文管理器。

        Args:
            level: 临时日志级别
        """
        self.new_level = LOG_LEVELS.get(level.upper(), logging.INFO)
        self.old_level: Optional[int] = None
        self.logger = logging.getLogger("chaosdroid")

    def __enter__(self) -> "LogLevelContext":
        """进入上下文，保存并设置新的日志级别。"""
        self.old_level = self.logger.level
        self.logger.setLevel(self.new_level)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """退出上下文，恢复原来的日志级别。"""
        if self.old_level is not None:
            self.logger.setLevel(self.old_level)