"""执行诊断集成服务。

将 ChaosDroid 执行记录与 TraceLens 诊断功能桥接。
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ScenarioRun, ScenarioTemplate
from app.diagnosis.services.ingest import IngestService
from app.diagnosis.services.diagnose import DiagnoseService
from app.diagnosis.schemas import DiagnosticResult

logger = logging.getLogger(__name__)


class ExecutionDiagnoseService:
    """执行诊断服务 - 桥接 ChaosDroid 和 TraceLens。"""

    def __init__(self, session: AsyncSession):
        """
        初始化服务。

        Args:
            session: 数据库会话
        """
        self.session = session
        self.ingest_service = IngestService(session)
        self.diagnose_service: Optional[DiagnoseService] = None

    async def diagnose_execution(
        self,
        run_id: int,
        artifacts_dir: Path,
    ) -> Optional[DiagnosticResult]:
        """
        对执行记录执行诊断。

        Args:
            run_id: ChaosDroid 执行记录 ID
            artifacts_dir: 执行产物目录

        Returns:
            诊断结果，如果诊断失败则返回 None
        """
        try:
            # 1. 获取执行记录
            from sqlalchemy import select
            stmt = select(ScenarioRun).where(ScenarioRun.id == run_id)
            result = await self.session.execute(stmt)
            execution_run = result.scalar_one_or_none()

            if not execution_run:
                logger.error(f"执行记录不存在：run_id={run_id}")
                return None

            # 2. 获取关联的场景模板
            template = None
            if execution_run.scenario_template_id:
                stmt = select(ScenarioTemplate).where(
                    ScenarioTemplate.id == execution_run.scenario_template_id
                )
                result = await self.session.execute(stmt)
                template = result.scalar_one_or_none()

            # 3. 构建元数据
            metadata = {
                "device_serial": execution_run.device_serial,
                "test_type": template.name if template else "unknown",
                "chaosdroid_run_id": str(run_id),
                "inject_stage": execution_run.inject_stage,
            }

            # 4. 导入日志到 TraceLens
            logger.info(f"导入执行产物到 TraceLens: run_id={run_id}, artifacts_dir={artifacts_dir}")

            if not artifacts_dir.exists():
                logger.warning(f"产物目录不存在：{artifacts_dir}")
                return None

            tracelens_run_id = await self.ingest_service.ingest_path(
                path=str(artifacts_dir),
                metadata=metadata,
            )
            logger.info(f"产物已导入到 TraceLens: tracelens_run_id={tracelens_run_id}")

            # 5. 执行诊断
            logger.info(f"执行诊断：tracelens_run_id={tracelens_run_id}")
            self.diagnose_service = DiagnoseService(self.session)
            diagnosis_result = await self.diagnose_service.diagnose(tracelens_run_id)
            logger.info(f"诊断完成：{diagnosis_result.category.value if diagnosis_result.category else 'N/A'}")

            return diagnosis_result

        except Exception as e:
            logger.exception(f"执行诊断失败：run_id={run_id}")
            return None

    def diagnose_result_to_dict(self, result: DiagnosticResult) -> Dict[str, Any]:
        """
        将诊断结果转换为字典。

        Args:
            result: 诊断结果

        Returns:
            字典格式的诊断结果
        """
        if not result:
            return {}

        return {
            "category": result.category.value if result.category else None,
            "root_cause": result.root_cause,
            "confidence": result.confidence,
            "result_status": result.result_status.value if result.result_status else None,
            "suggested_actions": result.suggested_actions or [],
            "similar_cases": [
                {
                    "case_id": case.case_id,
                    "similarity": case.similarity,
                    "root_cause": case.root_cause,
                }
                for case in (result.similar_cases or [])
            ],
        }
