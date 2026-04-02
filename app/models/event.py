"""
事件记录模型。

包含 IncidentEvent 模型定义，用于记录系统事件。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.sqlite import JSON

from .base import Base

if TYPE_CHECKING:
    from .scenario import ScenarioRun


class IncidentEvent(Base):
    """
    事件记录模型。

    记录系统中发生的各类事件，如设备离线、租约创建等。
    """

    __tablename__ = "incident_events"
    __table_args__ = (
        Index("ix_incident_events_event_type", "event_type"),
        Index("ix_incident_events_device_id", "device_id"),
        Index("ix_incident_events_scenario_run_id", "scenario_run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    device_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联设备ID",
    )
    scenario_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("scenario_runs.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联执行记录ID",
    )
    event_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="事件类型: device_offline/lease_created等",
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        default="info",
        nullable=False,
        comment="严重程度: info/warning/error/critical",
    )
    payload_json: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="事件详情JSON，包含事件的额外信息",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        nullable=False,
        comment="创建时间",
    )

    # 关系定义
    scenario_run: Mapped["ScenarioRun | None"] = relationship(
        "ScenarioRun",
        back_populates="incident_events",
    )

    def __repr__(self) -> str:
        return f"<IncidentEvent(id={self.id}, event_type='{self.event_type}', severity='{self.severity}')>"