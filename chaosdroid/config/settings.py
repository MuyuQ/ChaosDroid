"""ChaosDroid 配置管理模块。

使用 Pydantic BaseSettings 管理配置，支持环境变量覆盖。
环境变量前缀：CHAOSDROID_
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    return settings