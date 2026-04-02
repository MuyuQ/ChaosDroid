"""配置管理模块。"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置。"""

    # 数据库配置
    database_url: str = Field(
        default="sqlite+aiosqlite:///data/tracelens.db",
        description="数据库连接URL"
    )

    # 存储路径
    artifacts_base_path: Path = Field(
        default=Path("artifacts/raw"),
        description="原始证据存储路径"
    )
    data_base_path: Path = Field(
        default=Path("data"),
        description="数据目录路径"
    )

    # 规则配置
    rules_path: Path = Field(
        default=Path("src/tracelens/rules"),
        description="规则YAML文件路径"
    )

    # Web配置
    web_host: str = Field(default="127.0.0.1", description="Web服务主机")
    web_port: int = Field(default=8000, description="Web服务端口")

    # 案例召回配置
    similar_case_limit: int = Field(default=3, description="相似案例召回数量")

    # 相似度阈值配置
    similarity_threshold: float = Field(
        default=0.3,
        description="最低相似度阈值，低于此值的案例不会召回",
        ge=0.0,
        le=1.0,
    )
    similarity_root_cause_weight: float = Field(
        default=0.5,
        description="根因完全匹配的权重",
        ge=0.0,
        le=1.0,
    )
    similarity_category_weight: float = Field(
        default=0.2,
        description="分类匹配的权重",
        ge=0.0,
        le=1.0,
    )
    similarity_text_weight: float = Field(
        default=0.3,
        description="特征文本相似度的权重",
        ge=0.0,
        le=1.0,
    )

    # 置信度加分配置
    confidence_stage_span_threshold: int = Field(
        default=3,
        description="阶段跨度加分阈值，事件跨越至少多少个连续阶段才加分",
        ge=1,
    )
    confidence_stage_span_bonus: float = Field(
        default=0.05,
        description="阶段跨度加分值",
        ge=0.0,
        le=1.0,
    )
    confidence_multi_source_threshold: int = Field(
        default=2,
        description="多来源加分阈值，事件来自至少多少个不同来源才加分",
        ge=1,
    )
    confidence_multi_source_bonus: float = Field(
        default=0.03,
        description="多来源加分值",
        ge=0.0,
        le=1.0,
    )
    confidence_evidence_count_threshold: int = Field(
        default=3,
        description="关键证据数量加分阈值，匹配证据至少多少条才加分",
        ge=1,
    )
    confidence_evidence_count_bonus: float = Field(
        default=0.02,
        description="关键证据数量加分值",
        ge=0.0,
        le=1.0,
    )

    # 置信度扣分配置
    confidence_conflict_penalty: float = Field(
        default=0.05,
        description="多规则冲突时的每条竞争规则扣分系数",
        ge=0.0,
        le=1.0,
    )

    model_config = {
        "env_prefix": "TRACELENS_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


class Config(BaseModel):
    """运行时配置。"""

    settings: Settings = Field(default_factory=Settings)

    # 状态定义
    run_status_values: list[str] = Field(
        default=["pending", "imported", "parsed", "diagnosed", "failed", "passed"]
    )
    result_status_values: list[str] = Field(
        default=["pending", "passed", "failed", "transient_failure", "insufficient_evidence"]
    )

    # 文件类型识别规则
    file_type_patterns: dict[str, list[str]] = Field(
        default={
            "recovery_log": ["recovery.log", "recovery.txt"],
            "last_install": ["last_install.txt", "last_install"],
            "update_engine_log": ["update_engine.log", "update_engine.txt"],
            "device_runtime_log": ["logcat.txt", "logcat.log", "boot_check.txt", "monkey.txt", "validation.txt"],
            "artifact_summary": ["device_snapshot.json", "run_timeline.json", "perf_summary.json"],
        }
    )


# 全局配置实例
config = Config()
settings = Settings()