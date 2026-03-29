"""
执行产物和报告模型。

包含 Artifact 和 Report 模型定义。
"""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import ArtifactType, Base, TimestampMixin

if TYPE_CHECKING:
    from .scenario import ScenarioRun, ScenarioStep


class Artifact(Base, TimestampMixin):
    """
    执行产物模型。

    记录执行过程中产生的各类文件产物。
    """

    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    scenario_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("scenario_runs.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联执行记录ID",
    )
    step_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("scenario_steps.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联步骤ID",
    )
    artifact_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="产物类型: logcat/getprop/battery/monkey/stdout/stderr/snapshot/summary/other",
    )
    path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="文件路径",
    )
    size: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="文件大小（字节）",
    )
    meta_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="元数据JSON，包含产物的额外信息",
    )

    # 关系定义
    scenario_run: Mapped["ScenarioRun"] = relationship(
        "ScenarioRun",
        back_populates="artifacts",
    )
    step: Mapped["ScenarioStep | None"] = relationship(
        "ScenarioStep",
        back_populates="artifacts",
    )

    def __repr__(self) -> str:
        return f"<Artifact(id={self.id}, artifact_type='{self.artifact_type}', path='{self.path}')>"


class Report(Base, TimestampMixin):
    """
    报告记录模型。

    记录场景执行生成的报告信息。
    """

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    scenario_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("scenario_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="关联执行记录ID（一对一关系）",
    )
    markdown_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Markdown报告文件路径",
    )
    html_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="HTML报告文件路径",
    )
    summary_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="摘要JSON，包含报告的关键信息",
    )

    # 关系定义
    scenario_run: Mapped["ScenarioRun"] = relationship(
        "ScenarioRun",
        back_populates="report",
    )

    def __repr__(self) -> str:
        return f"<Report(id={self.id}, scenario_run_id={self.scenario_run_id})>"