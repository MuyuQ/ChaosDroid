"""
设备资源池模型。

定义设备池的数据库模型，用于管理设备资源分配。
"""

from sqlalchemy import Boolean, Float, Integer, String, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class DevicePool(Base, TimestampMixin):
    """
    设备池模型。

    用于管理设备资源的分组和分配策略。
    """

    __tablename__ = "device_pools"
    __table_args__ = (
        Index("ix_device_pools_name", "name", unique=True),
        Index("ix_device_pools_purpose", "purpose"),
        Index("ix_device_pools_enabled", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="主键")
    name: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        comment="设备池名称，唯一标识",
    )
    purpose: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="用途类型：stable/stress/emergency",
    )
    reserved_emergency_ratio: Mapped[float] = mapped_column(
        Float,
        default=0.2,
        nullable=False,
        comment="预留应急任务比例，默认 0.2",
    )
    max_parallel_jobs: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="最大并行任务数，为空表示不限制",
    )
    tag_selector_json: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="设备标签选择器 JSON，用于筛选符合条件的设备",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="是否启用",
    )

    def __repr__(self) -> str:
        return f"<DevicePool(id={self.id}, name='{self.name}', purpose='{self.purpose}')>"
