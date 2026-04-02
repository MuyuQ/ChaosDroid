"""诊断规则数据库模型。"""

from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, Integer, Boolean, Float, Enum as SQLEnum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.diagnosis.models.db import Base
from app.diagnosis.enums import Category

if TYPE_CHECKING:
    from app.diagnosis.models.hit import RuleHit


class DiagnosticRuleDB(Base):
    """诊断规则表。"""

    __tablename__ = "diagnostic_rule"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=50)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    match_all: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    match_any: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    exclude_any: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    match_stage: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    category: Mapped[Category] = mapped_column(SQLEnum(Category), nullable=False, index=True)
    root_cause: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    base_confidence: Mapped[float] = mapped_column(Float, default=0.9)
    next_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    hits: Mapped[list["RuleHit"]] = relationship(back_populates="rule")