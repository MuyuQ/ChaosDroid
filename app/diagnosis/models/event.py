"""标准化事件数据库模型。"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, Integer, Enum as SQLEnum, JSON, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.diagnosis.models.db import Base
from app.diagnosis.enums import Stage, SourceType, EventType, Severity

if TYPE_CHECKING:
    from app.diagnosis.models.run import DiagnosticRun


class NormalizedEventDB(Base):
    """标准化事件表。"""

    __tablename__ = "normalized_event"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("diagnostic_run.run_id"), nullable=False, index=True)
    device_serial: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_type: Mapped[SourceType] = mapped_column(SQLEnum(SourceType), nullable=False)
    timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    line_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    raw_line: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stage: Mapped[Stage] = mapped_column(SQLEnum(Stage), nullable=False, index=True)
    event_type: Mapped[EventType] = mapped_column(SQLEnum(EventType), nullable=False)
    severity: Mapped[Severity] = mapped_column(SQLEnum(Severity), nullable=False)
    normalized_code: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    kv_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    run: Mapped["DiagnosticRun"] = relationship(back_populates="events")

    # 复合索引
    __table_args__ = (
        Index("ix_normalized_event_run_stage", "run_id", "stage"),
        Index("ix_normalized_event_run_source", "run_id", "source_type"),
    )