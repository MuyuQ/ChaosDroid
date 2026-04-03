"""事件队列模型。

用于支持基于事件总成的解耦架构，实现执行服务与诊断服务的异步通信。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EventQueue(Base):
    """事件队列表。

    用于存储事件驱动架构中的异步任务队列，支持：
    - 任务完成事件发布
    - 后台消费者轮询处理
    - 重试机制
    """

    __tablename__ = "event_queue"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="主键 ID"
    )
    scenario_run_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        comment="关联的场景执行记录 ID"
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="事件类型（如 run_completed）"
    )
    payload_json: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="事件载荷（JSON 格式）"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        index=True,
        comment="状态：pending/processing/completed/failed"
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="优先级（值越大越优先）"
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="重试次数"
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="错误消息"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        comment="创建时间"
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="处理完成时间"
    )

    def __repr__(self) -> str:
        return (
            f"<EventQueue(id={self.id}, scenario_run_id={self.scenario_run_id}, "
            f"event_type={self.event_type}, status={self.status})>"
        )
