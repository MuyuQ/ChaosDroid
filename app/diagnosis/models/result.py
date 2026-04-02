"""诊断结果模型。"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, Float, Enum as SQLEnum, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.diagnosis.models.db import Base
from app.diagnosis.enums import Stage, ResultStatus, Category

if TYPE_CHECKING:
    from app.diagnosis.models.run import DiagnosticRun


class DiagnosticResultDB(Base):
    """诊断结果表。"""

    __tablename__ = "diagnostic_result"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("diagnostic_run.run_id"), unique=True, nullable=False, index=True)
    stage: Mapped[Stage] = mapped_column(SQLEnum(Stage), nullable=False)
    category: Mapped[Category] = mapped_column(SQLEnum(Category), nullable=False, index=True)
    root_cause: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    result_status: Mapped[ResultStatus] = mapped_column(SQLEnum(ResultStatus), nullable=False)
    key_evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    next_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    run: Mapped["DiagnosticRun"] = relationship(back_populates="result")