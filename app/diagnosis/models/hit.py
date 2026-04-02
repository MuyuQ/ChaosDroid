"""规则命中记录模型。"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, Float, JSON, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.diagnosis.models.db import Base

if TYPE_CHECKING:
    from app.diagnosis.models.run import DiagnosticRun
    from app.diagnosis.models.rule import DiagnosticRuleDB


class RuleHit(Base):
    """规则命中记录表。"""

    __tablename__ = "rule_hit"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("diagnostic_run.run_id"), nullable=False, index=True)
    rule_id: Mapped[str] = mapped_column(String(16), ForeignKey("diagnostic_rule.rule_id"), nullable=False, index=True)
    matched_event_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    run: Mapped["DiagnosticRun"] = relationship(back_populates="rule_hits")
    rule: Mapped["DiagnosticRuleDB"] = relationship(back_populates="hits")

    # 复合索引
    __table_args__ = (
        Index("ix_rule_hit_run_rule", "run_id", "rule_id"),
    )