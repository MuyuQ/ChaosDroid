"""ChaosDroid 配置管理模块。

使用 Pydantic BaseSettings 管理配置，支持环境变量覆盖。
环境变量前缀：CHAOSDROID_
"""

import logging
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class JsonFormatter(logging.Formatter):
    """JSON格式的日志格式化器."""

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录为JSON字符串."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "device_serial"):
            log_data["device_serial"] = record.device_serial
        if hasattr(record, "operation"):
            log_data["operation"] = record.operation

        return json.dumps(log_data, ensure_ascii=False)


class Settings(BaseSettings):
    """ChaosDroid 应用配置。

    所有配置项均可通过环境变量覆盖，环境变量格式为：
    CHAOSDROID_<配置项大写>
    例如：CHAOSDROID_DATABASE_PATH=/path/to/db

    Attributes:
        database_path: 数据库文件路径
        artifacts_dir: 执行产物存储目录
        reports_dir: 报告输出目录
        adb_path: ADB 可执行文件路径
        default_timeout: 默认操作超时时间（秒）
        web_port: Web 服务端口
        log_level: 日志级别
        log_format: 日志格式（text 或 json）
        log_format_string: 自定义日志格式字符串
        dangerous_operations_require_confirm: 危险操作是否需要确认
    """

    # 数据库配置
    database_path: str = Field(
        default="chaosdroid.db",
        description="SQLite 数据库文件路径",
    )

    # 目录配置
    artifacts_dir: str = Field(
        default="artifacts/",
        description="执行产物存储目录（logcat、monkey输出等）",
    )
    reports_dir: str = Field(
        default="reports/",
        description="测试报告输出目录",
    )

    # ADB 配置
    adb_path: str = Field(
        default="adb",
        description="ADB 可执行文件路径，可以是相对路径或绝对路径",
    )

    # 超时配置
    default_timeout: int = Field(
        default=120,
        ge=1,
        description="默认操作超时时间（秒），用于ADB操作等",
    )

    # Web 服务配置
    web_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Web 服务监听端口",
    )

    # 日志配置
    log_level: str = Field(
        default="INFO",
        description="日志级别：DEBUG、INFO、WARNING、ERROR、CRITICAL",
    )
    log_format: str = Field(
        default="text",
        description="日志格式：text（标准文本格式）或 json（JSON格式，适合日志聚合）",
    )
    log_format_string: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="自定义日志格式字符串，仅当 log_format=text 时有效",
    )

    # 安全配置
    dangerous_operations_require_confirm: bool = Field(
        default=True,
        description="危险操作（重启设备、清理存储等）是否需要用户确认",
    )

    model_config = SettingsConfigDict(
        env_prefix="CHAOSDROID_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """验证日志级别是否有效."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}, got: {v}")
        return v_upper

    @field_validator("log_format", mode="before")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        """验证日志格式是否有效."""
        valid_formats = ["text", "json"]
        v_lower = v.lower()
        if v_lower not in valid_formats:
            raise ValueError(f"log_format must be one of {valid_formats}, got: {v}")
        return v_lower

    def get_database_path(self) -> Path:
        """获取数据库文件的绝对路径。"""
        return Path(self.database_path).resolve()

    def get_artifacts_dir(self) -> Path:
        """获取执行产物目录的绝对路径。"""
        return Path(self.artifacts_dir).resolve()

    def get_reports_dir(self) -> Path:
        """获取报告目录的绝对路径。"""
        return Path(self.reports_dir).resolve()

    def ensure_directories(self) -> None:
        """确保所有必需的目录存在。"""
        self.get_artifacts_dir().mkdir(parents=True, exist_ok=True)
        self.get_reports_dir().mkdir(parents=True, exist_ok=True)

    def get_log_level_numeric(self) -> int:
        """获取日志级别的数值表示。"""
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        return level_map.get(self.log_level.upper(), logging.INFO)

    def get_log_formatter(self) -> logging.Formatter:
        """获取日志格式化器.

        根据配置返回文本格式或JSON格式的格式化器。

        Returns:
            logging.Formatter: 日志格式化器实例
        """
        if self.log_format.lower() == "json":
            return JsonFormatter()
        return logging.Formatter(self.log_format_string)

    def configure_logging(self, logger_name: Optional[str] = None) -> None:
        """配置应用日志.

        Args:
            logger_name: 可选的日志器名称，默认配置根日志器
        """
        logger = logging.getLogger(logger_name)
        logger.setLevel(self.get_log_level_numeric())

        # 如果已有处理器，更新格式化器
        for handler in logger.handlers:
            handler.setFormatter(self.get_log_formatter())

        # 如果没有处理器，添加一个
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(self.get_log_level_numeric())
            handler.setFormatter(self.get_log_formatter())
            logger.addHandler(handler)


@lru_cache
def get_settings() -> Settings:
    """获取配置单例。

    使用 lru_cache 确保配置只加载一次。
    在应用启动时调用此函数获取配置实例。

    Returns:
        Settings: 配置实例
    """
    settings = Settings()
    # 确保必要的目录存在
    settings.ensure_directories()
    # 配置日志
    settings.configure_logging("chaosdroid")
    return settings


__all__ = [
    "Settings",
    "get_settings",
    "JsonFormatter",
]