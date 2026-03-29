"""
场景模板和执行记录模型。

包含 ScenarioTemplate、ScenarioRun 和 ScenarioStep 模型定义。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, InjectStage, RunStatus, StepStatus, StepType, TargetType, ExecutorMode, TimestampMixin

if TYPE_CHECKING:
    from .artifact import Artifact, Report
    from .profiles import FaultProfile, RecoveryProfile, ValidationProfile


class ScenarioTemplate(Base, TimestampMixin):
    """
    场景模板模型。

    定义可复用的故障测试场景配置。
    """

    __tablename__ = "scenario_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="场景名称")
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="场景描述",
    )
    target_type: Mapped[str] = mapped_column(
        String(50),
        default=TargetType.STABILITY.value,
        nullable=False,
        comment="目标类型: upgrade/stability/monkey/recovery",
    )
    fault_profile_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("fault_profiles.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联故障配置ID",
    )
    inject_stage: Mapped[str] = mapped_column(
        String(50),
        default=InjectStage.PRECHECK.value,
        nullable=False,
        comment="注入阶段: precheck/prepare/upgrading/reboot_wait/post_boot/post_validate",
    )
    validation_profile_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("validation_profiles.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联验证配置ID",
    )
    recovery_profile_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("recovery_profiles.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联恢复配置ID",
    )
    executor_mode: Mapped[str] = mapped_column(
        String(20),
        default=ExecutorMode.MOCK.value,
        nullable=False,
        comment="执行器模式: real/mock",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="是否启用",
    )

    # 关系定义
    fault_profile: Mapped["FaultProfile | None"] = relationship(
        "FaultProfile",
        back_populates="scenario_templates",
    )
    validation_profile: Mapped["ValidationProfile | None"] = relationship(
        "ValidationProfile",
        back_populates="scenario_templates",
    )
    recovery_profile: Mapped["RecoveryProfile | None"] = relationship(
        "RecoveryProfile",
        back_populates="scenario_templates",
    )

    # 反向关系：关联的执行记录
    runs: Mapped[list["ScenarioRun"]] = relationship(
        "ScenarioRun",
        back_populates="scenario_template",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ScenarioTemplate(id={self.id}, name='{self.name}', target_type='{self.target_type}')>"


class ScenarioRun(Base, TimestampMixin):
    """
    场景执行记录模型。

    记录每次场景执行的完整信息。
    """

    __tablename__ = "scenario_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    scenario_template_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("scenario_templates.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联场景模板ID",
    )
    device_serial: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="设备序列号",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=RunStatus.QUEUED.value,
        nullable=False,
        comment="执行状态: queued/preparing/injecting/validating/recovering/passed/failed/partial",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="开始时间",
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="结束时间",
    )
    inject_stage: Mapped[str] = mapped_column(
        String(50),
        default=InjectStage.PRECHECK.value,
        nullable=False,
        comment="注入阶段",
    )
    result_summary_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="结果摘要JSON，包含执行结果的详细信息",
    )

    # 关系定义
    scenario_template: Mapped["ScenarioTemplate | None"] = relationship(
        "ScenarioTemplate",
        back_populates="runs",
    )

    # 反向关系：关联的执行步骤
    steps: Mapped[list["ScenarioStep"]] = relationship(
        "ScenarioStep",
        back_populates="scenario_run",
        cascade="all, delete-orphan",
        order_by="ScenarioStep.step_order",
    )

    # 反向关系：关联的产物
    artifacts: Mapped[list["Artifact"]] = relationship(
        "Artifact",
        back_populates="scenario_run",
        cascade="all, delete-orphan",
    )

    # 反向关系：关联的报告
    report: Mapped["Report | None"] = relationship(
        "Report",
        back_populates="scenario_run",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ScenarioRun(id={self.id}, device_serial='{self.device_serial}', status='{self.status}')>"


class ScenarioStep(Base, TimestampMixin):
    """
    执行步骤记录模型。

    记录场景执行中每个步骤的详细信息。
    """

    __tablename__ = "scenario_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    scenario_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("scenario_runs.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联执行记录ID",
    )
    step_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="步骤类型: precheck/inject/observe/validate/recover/collect",
    )
    step_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="步骤顺序",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=StepStatus.PENDING.value,
        nullable=False,
        comment="步骤状态: pending/running/success/failed/skipped/timeout",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="开始时间",
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="结束时间",
    )
    summary_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="步骤摘要JSON，包含步骤执行的详细信息",
    )

    # 关系定义
    scenario_run: Mapped["ScenarioRun"] = relationship(
        "ScenarioRun",
        back_populates="steps",
    )

    # 反向关系：关联的产物
    artifacts: Mapped[list["Artifact"]] = relationship(
        "Artifact",
        back_populates="step",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ScenarioStep(id={self.id}, step_type='{self.step_type}', step_order={self.step_order}, status='{self.status}')>"