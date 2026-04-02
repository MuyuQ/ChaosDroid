"""原始证据文件模型。"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, Integer, Enum as SQLEnum, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.diagnosis.models.db import Base
from app.diagnosis.enums import SourceType

if TYPE_CHECKING:
    from app.diagnosis.models.run import DiagnosticRun


class RawArtifact(Base):
    """原始证据文件索引表。"""

    __tablename__ = "raw_artifact"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("diagnostic_run.run_id"), nullable=False, index=True)
    source_type: Mapped[SourceType] = mapped_column(SQLEnum(SourceType), nullable=False)
    file_name: Mapped[str] = mapped_column(String(256), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    run: Mapped["DiagnosticRun"] = relationship(back_populates="artifacts")

    # 复合索引
    __table_args__ = (
        Index("ix_raw_artifact_run_source", "run_id", "source_type"),
    )