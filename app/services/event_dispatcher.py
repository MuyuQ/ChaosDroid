"""事件分发器服务。

基于 SQLite 队列实现轻量级事件总线，支持执行服务与诊断服务的解耦通信。
"""

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.event_queue import EventQueue

logger = logging.getLogger(__name__)


class EventDispatcher:
    """事件分发器。

    负责发布事件到队列，供后台消费者处理。

    使用场景:
        # 在 ExecutionService 中发布任务完成事件
        dispatcher = EventDispatcher(session)
        await dispatcher.publish_run_completed(scenario_run_id=123)
    """

    def __init__(self, session: AsyncSession):
        """初始化和创建事件分发器。

        Args:
            session: 异步数据库会话
        """
        self.session = session

    async def publish_run_completed(self, scenario_run_id: int) -> EventQueue:
        """发布任务完成事件。

        当场景执行完成时调用，触发后续的诊断流程。

        Args:
            scenario_run_id: 场景执行记录 ID

        Returns:
            EventQueue: 创建的事件记录
        """
        event = EventQueue(
            scenario_run_id=scenario_run_id,
            event_type="run_completed",
            payload_json=json.dumps({
                "scenario_run_id": scenario_run_id,
                "timestamp": datetime.utcnow().isoformat(),
            }),
            status="pending",
            priority=0,
        )
        self.session.add(event)
        await self.session.commit()

        logger.info(f"已发布任务完成事件：scenario_run_id={scenario_run_id}")
        return event

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        scenario_run_id: int | None = None,
        priority: int = 0,
    ) -> EventQueue:
        """发布通用事件。

        Args:
            event_type: 事件类型
            payload: 事件载荷
            scenario_run_id: 关联的场景执行记录 ID（可选）
            priority: 优先级（可选，默认 0）

        Returns:
            EventQueue: 创建的事件记录
        """
        event = EventQueue(
            scenario_run_id=scenario_run_id or 0,
            event_type=event_type,
            payload_json=json.dumps(payload),
            status="pending",
            priority=priority,
        )
        self.session.add(event)
        await self.session.commit()

        logger.info(f"已发布事件：type={event_type}, scenario_run_id={scenario_run_id}")
        return event

    async def get_pending_events(
        self,
        event_type: str | None = None,
        batch_size: int = 10,
    ) -> list[EventQueue]:
        """获取待处理事件。

        Args:
            event_type: 事件类型过滤（可选）
            batch_size: 批次大小

        Returns:
            list[EventQueue]: 待处理事件列表
        """
        stmt = select(EventQueue).where(
            EventQueue.status == "pending"
        )

        if event_type:
            stmt = stmt.where(EventQueue.event_type == event_type)

        stmt = stmt.order_by(
            EventQueue.priority.desc(),
            EventQueue.created_at.asc(),
        ).limit(batch_size)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_processing(self, event_id: int) -> None:
        """标记事件为处理中。

        Args:
            event_id: 事件 ID
        """
        event = await self._get_event(event_id)
        if event:
            event.status = "processing"
            await self.session.commit()

    async def mark_completed(self, event_id: int) -> None:
        """标记事件为已完成。

        Args:
            event_id: 事件 ID
        """
        event = await self._get_event(event_id)
        if event:
            event.status = "completed"
            event.processed_at = datetime.utcnow()
            await self.session.commit()

    async def mark_failed(self, event_id: int, error_message: str) -> None:
        """标记事件为失败。

        Args:
            event_id: 事件 ID
            error_message: 错误消息
        """
        event = await self._get_event(event_id)
        if event:
            event.status = "failed"
            event.error_message = error_message
            event.retry_count += 1
            await self.session.commit()

    async def _get_event(self, event_id: int) -> EventQueue | None:
        """获取事件。

        Args:
            event_id: 事件 ID

        Returns:
            EventQueue 或 None
        """
        stmt = select(EventQueue).where(EventQueue.id == event_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
