"""ChaosDroid 配置管理包。

提供应用配置和日志配置。

Example:
    >>> from chaosdroid.config import get_settings, setup_logging
    >>> settings = get_settings()
    >>> print(settings.database_path)
    chaosdroid.db
    >>> setup_logging()
"""

from .logging import (
    LOG_FORMAT,
    LOG_LEVELS,
    LogLevelContext,
    get_logger,
    log_startup_info,
    setup_logging,
)
from .settings import Settings, get_settings

__all__ = [
    # Settings
    "Settings",
    "get_settings",
    # Logging
    "setup_logging",
    "get_logger",
    "log_startup_info",
    "LogLevelContext",
    "LOG_FORMAT",
    "LOG_LEVELS",
]