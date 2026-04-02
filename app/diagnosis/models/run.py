"""诊断任务模型。"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.diagnosis.models.db import Base
from app.diagnosis.enums import RunStatus

if TYPE_CHECKING:
    from app.diagnosis.models.artifact import RawArtifact
    from app.diagnosis.models.event import NormalizedEventDB
    from app.diagnosis.models.hit import RuleHit
    from app.diagnosis.models.result import DiagnosticResultDB
    from app.diagnosis.models.case import SimilarCaseIndex, CaseLink


class DiagnosticRun(Base):
    """诊断任务表。"""

    __tablename__ = "diagnostic_run"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    device_serial: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    test_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    build_fingerprint: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    import_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RunStatus] = mapped_column(SQLEnum(RunStatus), default=RunStatus.PENDING)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    artifacts: Mapped[list["RawArtifact"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    events: Mapped[list["NormalizedEventDB"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    rule_hits: Mapped[list["RuleHit"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    result: Mapped[Optional["DiagnosticResultDB"]] = relationship(back_populates="run", cascade="all, delete-orphan", uselist=False)
    similar_case_index: Mapped[Optional["SimilarCaseIndex"]] = relationship(back_populates="run", cascade="all, delete-orphan", uselist=False)
    case_links_as_source: Mapped[list["CaseLink"]] = relationship(back_populates="run", foreign_keys="CaseLink.run_id", cascade="all, delete-orphan")