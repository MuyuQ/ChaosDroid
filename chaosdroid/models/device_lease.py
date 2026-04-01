"""
设备租约模型。

定义 DeviceLease 模型，用于设备独占锁定机制。
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .scenario import ScenarioRun


class DeviceLease(Base, TimestampMixin):
    """
    设备租约模型。

    用于设备的独占锁定机制，防止同一设备上的并发执行。
    支持租约超时、抢占和释放。
    """

    __tablename__ = "device_leases"
    __table_args__ = (
        Index("ix_device_leases_device_id", "device_id"),
        Index("ix_device_leases_scenario_run_id", "scenario_run_id"),
        Index("ix_device_leases_lease_status", "lease_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    device_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联设备ID",
    )
    scenario_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("scenario_runs.id", ondelete="SET NULL"),
        nullable=True,
        comment="关联场景执行记录ID",
    )
    lease_status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        nullable=False,
        comment="租约状态: active/released/preempted/expired",
    )
    leased_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="租约获取时间",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="租约过期时间",
    )
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="租约释放时间",
    )
    preemptible: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="是否可被抢占",
    )

    # 关系定义
    scenario_run: Mapped["ScenarioRun | None"] = relationship(
        "ScenarioRun",
        back_populates="device_leases",
        foreign_keys=[scenario_run_id],
    )

    def __repr__(self) -> str:
        return f"<DeviceLease(id={self.id}, device_id={self.device_id}, lease_status='{self.lease_status}')>"