"""
故障配置、验证配置和恢复配置模型。

包含 FaultProfile、ValidationProfile 和 RecoveryProfile 模型定义。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, FaultType, RiskLevel, TimestampMixin

if TYPE_CHECKING:
    from .scenario import ScenarioTemplate


class FaultProfile(Base, TimestampMixin):
    """
    故障注入配置模型。

    定义故障类型、参数和风险等级。
    """

    __tablename__ = "fault_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="配置名称")
    fault_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="故障类型",
    )
    parameters_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="参数JSON，包含故障注入的具体配置",
    )
    safe_cleanup_required: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="是否需要安全清理",
    )
    risk_level: Mapped[str] = mapped_column(
        String(20),
        default=RiskLevel.LOW.value,
        nullable=False,
        comment="风险等级: low/medium/high/critical",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="配置描述",
    )

    # 反向关系：关联的场景模板
    scenario_templates: Mapped[list["ScenarioTemplate"]] = relationship(
        "ScenarioTemplate",
        back_populates="fault_profile",
    )

    def __repr__(self) -> str:
        return f"<FaultProfile(id={self.id}, name='{self.name}', fault_type='{self.fault_type}')>"


class ValidationProfile(Base, TimestampMixin):
    """
    验证配置模型。

    定义验证检查项、超时和通过规则。
    """

    __tablename__ = "validation_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="配置名称")
    checks_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="检查项JSON，包含验证检查的配置列表",
    )
    timeout_sec: Mapped[int] = mapped_column(
        Integer,
        default=180,
        nullable=False,
        comment="验证超时时间（秒）",
    )
    pass_rules_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="通过规则JSON，定义验证通过的判定条件",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="配置描述",
    )

    # 反向关系：关联的场景模板
    scenario_templates: Mapped[list["ScenarioTemplate"]] = relationship(
        "ScenarioTemplate",
        back_populates="validation_profile",
    )

    def __repr__(self) -> str:
        return f"<ValidationProfile(id={self.id}, name='{self.name}')>"


class RecoveryProfile(Base, TimestampMixin):
    """
    恢复策略配置模型。

    定义恢复步骤和超时配置。
    """

    __tablename__ = "recovery_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="配置名称")
    steps_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="恢复步骤JSON，包含恢复操作的配置列表",
    )
    manual_intervention_allowed: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="是否允许人工介入",
    )
    timeout_sec: Mapped[int] = mapped_column(
        Integer,
        default=300,
        nullable=False,
        comment="恢复超时时间（秒）",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="配置描述",
    )

    # 反向关系：关联的场景模板
    scenario_templates: Mapped[list["ScenarioTemplate"]] = relationship(
        "ScenarioTemplate",
        back_populates="recovery_profile",
    )

    def __repr__(self) -> str:
        return f"<RecoveryProfile(id={self.id}, name='{self.name}')>"