"""相似案例模型。"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, Float, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.diagnosis.models.db import Base
from app.diagnosis.enums import Category

if TYPE_CHECKING:
    from app.diagnosis.models.run import DiagnosticRun


class SimilarCaseIndex(Base):
    """历史案例特征索引表。"""

    __tablename__ = "similar_case_index"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("diagnostic_run.run_id"), unique=True, nullable=False, index=True)
    category: Mapped[Category] = mapped_column(SQLEnum(Category), nullable=False, index=True)
    root_cause: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    feature_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_code_signature: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    run: Mapped["DiagnosticRun"] = relationship(back_populates="similar_case_index")


class CaseLink(Base):
    """案例关联表。"""

    __tablename__ = "case_link"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("diagnostic_run.run_id"), nullable=False, index=True)
    similar_run_id: Mapped[str] = mapped_column(String(64), ForeignKey("diagnostic_run.run_id"), nullable=False, index=True)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    run: Mapped["DiagnosticRun"] = relationship(back_populates="case_links_as_source", foreign_keys="[CaseLink.run_id]")
    similar_run: Mapped["DiagnosticRun"] = relationship(foreign_keys="[CaseLink.similar_run_id]")