"""诊断后台 Worker。

轮询事件队列，触发日志导出和诊断分析。
"""

import asyncio
import logging

from app.diagnosis.services.trigger import DiagnosisTrigger
from app.models.database import get_session_context

logger = logging.getLogger(__name__)


class DiagnosisWorker:
    """诊断后台 Worker。

    使用轮询方式检查事件队列，处理待诊断任务。
    """

    def __init__(self, poll_interval_sec: int = 5, batch_size: int = 10):
        """初始化诊断 Worker。

        Args:
            poll_interval_sec: 轮询间隔（秒）
            batch_size: 批次处理大小
        """
        self.poll_interval_sec = poll_interval_sec
        self.batch_size = batch_size
        self.running = False

    async def start(self) -> None:
        """启动 Worker 循环。"""
        self.running = True
        logger.info(
            f"DiagnosisWorker 已启动，poll_interval={self.poll_interval_sec}s, batch_size={self.batch_size}"
        )

        while self.running:
            try:
                async with get_session_context() as session:
                    trigger = DiagnosisTrigger(session)
                    processed_count = await trigger.poll_and_process(
                        batch_size=self.batch_size
                    )

                    if processed_count > 0:
                        logger.info(f"本批次处理了 {processed_count} 个诊断任务")

            except Exception as e:
                logger.exception(f"诊断任务执行失败：error={e}")

            await asyncio.sleep(self.poll_interval_sec)

    async def stop(self) -> None:
        """停止 Worker。"""
        self.running = False
        logger.info("DiagnosisWorker 停止中...")
