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
    DEFAULT_LOG_FORMAT,
    DEFAULT_DATE_FORMAT,
    LOG_LEVELS,
    LogLevelContext,
    get_logger,
    log_startup_info,
    setup_logging,
    load_log_format_from_env,
    load_log_file_from_env,
    load_log_backup_count_from_env,
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
    "DEFAULT_LOG_FORMAT",
    "DEFAULT_DATE_FORMAT",
    "LOG_LEVELS",
    "load_log_format_from_env",
    "load_log_file_from_env",
    "load_log_backup_count_from_env",
]