"""
设备模型。

包含 Device 模型定义，用于管理测试设备的状态和健康信息。
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    pass


class Device(Base, TimestampMixin):
    """
    设备模型。

    管理测试设备的状态、健康信息和池归属。
    """

    __tablename__ = "devices"
    __table_args__ = (
        Index("ix_devices_serial", "serial", unique=True),
        Index("ix_devices_status", "status"),
        Index("ix_devices_health_score", "health_score"),
        Index("ix_devices_status_health_score", "status", "health_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    serial: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="设备序列号，唯一标识",
    )
    model: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="设备型号",
    )
    brand: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="设备品牌",
    )
    android_version: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="Android版本",
    )
    build_fingerprint: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
        comment="系统构建指纹",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="idle",
        nullable=False,
        comment="设备状态: idle/reserved/busy/offline/quarantined/recovering",
    )
    health_score: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="健康分数(0-100)",
    )
    battery_level: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="电池电量百分比",
    )
    pool_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("device_pools.id", ondelete="SET NULL"),
        nullable=True,
        comment="所属设备池ID",
    )
    tags_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="设备标签JSON数组",
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="最后在线时间",
    )
    quarantine_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="隔离原因",
    )
    executor_mode: Mapped[str] = mapped_column(
        String(20),
        default="mock",
        nullable=False,
        comment="执行器模式: real/mock",
    )
    sync_failure_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="同步失败计数",
    )

    def __repr__(self) -> str:
        return f"<Device(id={self.id}, serial='{self.serial}', status='{self.status}', health_score={self.health_score})>"