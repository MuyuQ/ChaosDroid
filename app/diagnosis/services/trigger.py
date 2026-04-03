"""诊断触发器服务。

用于轮询事件队列，触发日志导出和诊断分析流程。
"""

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_queue import EventQueue
from app.services.log_export_service import LogExportService
from app.diagnosis.services.ingest import IngestService
from app.diagnosis.services.diagnose import DiagnoseService

logger = logging.getLogger(__name__)


class DiagnosisTrigger:
    """诊断触发器。

    后台消费者，负责:
    1. 轮询待处理的事件队列
    2. 触发日志导出
    3. 导入诊断系统
    4. 执行诊断分析
    5. 保存诊断结果
    """

    def __init__(self, session: AsyncSession):
        """初始化诊断触发器。

        Args:
            session: 异步数据库会话
        """
        self.session = session
        self.export_service = LogExportService(session)
        self.ingest_service = IngestService(session)
        self.diagnose_service = DiagnoseService(session)

    async def poll_and_process(self, batch_size: int = 10) -> int:
        """轮询队列并处理任务。

        Args:
            batch_size: 批次处理大小

        Returns:
            int: 处理的任务数量
        """
        tasks = await self._fetch_pending_tasks(batch_size)
        processed_count = 0

        for task in tasks:
            try:
                await self._process_task(task)
                processed_count += 1
            except Exception as e:
                logger.exception(f"处理诊断任务失败：task_id={task.id}, error={e}")
                # 标记为失败，允许重试
                task.status = "failed"
                task.error_message = str(e)
                task.retry_count += 1
                await self.session.commit()

        return processed_count

    async def _fetch_pending_tasks(self, batch_size: int) -> list[EventQueue]:
        """获取待处理任务。

        Args:
            batch_size: 批次大小

        Returns:
            list[EventQueue]: 待处理任务列表
        """
        stmt = (
            select(EventQueue)
            .where(EventQueue.status == "pending")
            .where(EventQueue.event_type == "run_completed")
            .order_by(
                EventQueue.priority.desc(),
                EventQueue.created_at.asc(),
            )
            .limit(batch_size)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _process_task(self, task: EventQueue) -> None:
        """处理单个诊断任务。

        Args:
            task: 事件队列任务
        """
        run_id = task.payload_json.get("scenario_run_id")
        if not run_id:
            logger.error(f"任务载荷缺少 scenario_run_id: task_id={task.id}")
            task.status = "failed"
            task.error_message = "Missing scenario_run_id in payload"
            return

        logger.info(f"开始处理诊断任务：task_id={task.id}, scenario_run_id={run_id}")

        # 标记为处理中
        task.status = "processing"
        await self.session.commit()

        try:
            # 1. 导出日志
            export_path = await self.export_service.export_full_snapshot(run_id)
            if not export_path:
                raise Exception(f"Failed to export logs for scenario_run_id={run_id}")

            logger.info(f"日志导出完成：scenario_run_id={run_id}, path={export_path}")

            # 2. 调用诊断服务
            # 注意：这里需要调用 TraceLens 的导入和诊断服务
            # 由于诊断服务可能还在适配中，这里先记录日志
            diagnosis_result = await self._run_diagnosis(run_id, export_path)

            # 3. 保存诊断结果
            await self._save_diagnosis_result(run_id, diagnosis_result)

            # 4. 更新队列状态
            task.status = "completed"
            task.processed_at = datetime.utcnow()
            logger.info(f"诊断任务完成：task_id={task.id}, scenario_run_id={run_id}")

        except Exception as e:
            logger.exception(f"诊断任务执行失败：task_id={task.id}, scenario_run_id={run_id}")
            task.status = "failed"
            task.error_message = str(e)
            task.retry_count += 1

        await self.session.commit()

    async def _run_diagnosis(self, run_id: int, export_path: Path) -> dict:
        """执行诊断分析。

        Args:
            run_id: 场景执行记录 ID
            export_path: 日志导出路径

        Returns:
            dict: 诊断结果
        """
        logger.info(f"执行诊断分析：scenario_run_id={run_id}, logs={export_path}")

        try:
            # 1. 导入日志到诊断系统
            diagnosis_run_id = await self.ingest_service.ingest_path(
                str(export_path),
                metadata={"scenario_run_id": run_id, "device_serial": getattr(export_path, 'device_serial', None)},
            )
            logger.info(f"日志导入完成：diagnosis_run_id={diagnosis_run_id}")

            # 2. 执行诊断分析
            from app.diagnosis.exceptions import NotFoundError, DiagnosisError
            result = await self.diagnose_service.diagnose(diagnosis_run_id)
            logger.info(f"诊断分析完成：diagnosis_run_id={diagnosis_run_id}, category={result.category}")

            # 注意：DiagnosticResult 的 category 是字符串，不需要 .value
            return {
                "status": "completed",
                "diagnosis_run_id": diagnosis_run_id,
                "category": result.category,  # 已经是字符串
                "root_cause": result.root_cause,
                "confidence": result.confidence,  # 0-1 的 float
                "result_status": result.result_status.value if result.result_status else None,
            }

        except (NotFoundError, DiagnosisError) as e:
            logger.warning(f"诊断服务执行失败：scenario_run_id={run_id}, error={e}")
            return {
                "status": "failed",
                "message": str(e),
                "export_path": str(export_path),
            }
        except Exception as e:
            logger.exception(f"诊断服务异常：scenario_run_id={run_id}, error={e}")
            return {
                "status": "failed",
                "message": str(e),
                "export_path": str(export_path),
            }

    async def _save_diagnosis_result(
        self,
        run_id: int,
        diagnosis_result: dict,
    ) -> None:
        """保存诊断结果到 ScenarioRun。

        Args:
            run_id: 场景执行记录 ID
            diagnosis_result: 诊断结果
        """
        from app.models.scenario import ScenarioRun

        # 获取执行记录
        stmt = select(ScenarioRun).where(ScenarioRun.id == run_id)
        result = await self.session.execute(stmt)
        run = result.scalar_one_or_none()

        if not run:
            logger.warning(f"未找到场景执行记录：scenario_run_id={run_id}")
            return

        # 更新诊断结果字段
        if diagnosis_result.get("status") == "completed":
            run.diagnosis_run_id = diagnosis_result.get("diagnosis_run_id")
            run.diagnosis_category = diagnosis_result.get("category")
            run.diagnosis_root_cause = diagnosis_result.get("root_cause")
            run.diagnosis_confidence = diagnosis_result.get("confidence")
            run.diagnosis_completed_at = datetime.utcnow()
            logger.info(
                f"诊断结果已保存：scenario_run_id={run_id}, "
                f"category={run.diagnosis_category}, "
                f"confidence={run.diagnosis_confidence}"
            )
        else:
            logger.warning(f"诊断任务未完成，不保存结果：scenario_run_id={run_id}, message={diagnosis_result.get('message')}")
