"""诊断服务 - 异步版本。"""

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.diagnosis.engine import RuleEngine
from app.diagnosis.enums import RunStatus, Category
from app.diagnosis.exceptions import NotFoundError, DiagnosisError
from app.diagnosis.models import DiagnosticRun, DiagnosticResultDB, RuleHit
from app.diagnosis.schemas import DiagnosticResult
from app.diagnosis.services.parse import ParseService
from app.diagnosis.services.rule import RuleService
from app.diagnosis.services.similar import SimilarCaseService


class DiagnoseService:
    """诊断服务。"""

    def __init__(self, session: AsyncSession, rules=None):
        """
        初始化服务。

        Args:
            session: 数据库会话
            rules: 预加载的规则列表，如果为 None 则在 diagnose 时加载
        """
        self.session = session
        self.parse_service = ParseService(session)
        self.rule_engine = RuleEngine(rules=rules) if rules else None
        self.rule_service = RuleService(session)
        self.similar_service = SimilarCaseService(session)

    async def _ensure_rules_loaded(self):
        """确保规则已加载。"""
        if self.rule_engine is None:
            rules = await self.rule_service.load_rules_for_engine()
            self.rule_engine = RuleEngine(rules=rules)

    async def diagnose(self, run_id: str) -> DiagnosticResult:
        """
        对指定任务执行诊断。

        Args:
            run_id: 任务 ID

        Returns:
            诊断结果

        Raises:
            NotFoundError: 任务不存在
            DiagnosisError: 诊断执行失败
        """
        # 获取任务
        stmt = select(DiagnosticRun).where(DiagnosticRun.run_id == run_id)
        result = await self.session.execute(stmt)
        run = result.scalar_one_or_none()

        if not run:
            raise NotFoundError(f"任务不存在：{run_id}", {"run_id": run_id})

        try:
            # 确保规则已加载
            await self._ensure_rules_loaded()

            # 解析事件（如果尚未解析）
            events = await self.parse_service.get_events(run_id)
            if not events:
                events = await self.parse_service.parse_run(run_id)

            # 执行规则匹配，获取匹配的规则列表
            diag_result, matched_rules = self.rule_engine.evaluate(run_id, events)

            if not diag_result:
                raise DiagnosisError(f"规则引擎未能生成诊断结果", {"run_id": run_id})

            # 保存结果
            await self._save_result(diag_result)

            # 保存规则命中记录
            await self._save_rule_hits(run_id, matched_rules, events)

            # 索引结果用于相似案例召回
            await self.similar_service.index_run(diag_result)

            # 更新任务状态
            run.status = RunStatus.DIAGNOSED
            run.finished_at = datetime.utcnow()
            await self.session.commit()

            return diag_result

        except NotFoundError:
            # NotFoundError 直接向上传递
            await self.session.rollback()
            raise
        except DiagnosisError:
            # DiagnosisError 直接向上传递
            await self.session.rollback()
            raise
        except Exception as e:
            # 其他异常转换为 DiagnosisError
            await self.session.rollback()
            raise DiagnosisError(f"诊断执行失败：{str(e)}", {"run_id": run_id, "error": str(e)})

    async def _save_rule_hits(
        self,
        run_id: str,
        matched_rules: list,
        events: list,
    ) -> None:
        """
        保存规则命中记录。

        Args:
            run_id: 任务 ID
            matched_rules: 匹配的规则列表
            events: 标准化事件列表
        """
        for rule in matched_rules:
            # 收集匹配的事件 ID
            matched_event_ids = [
                e.id for e in events
                if e.normalized_code in rule.match_all + rule.match_any
            ]

            # 计算得分（基于匹配事件数量）
            score = len(matched_event_ids) / max(len(events), 1) if events else 0.0

            hit = RuleHit(
                run_id=run_id,
                rule_id=rule.rule_id,
                matched_event_ids=matched_event_ids,
                score=score,
            )
            self.session.add(hit)

    async def _save_result(self, result: DiagnosticResult) -> None:
        """保存诊断结果。"""
        # 将字符串 category 转换为 Category 枚举
        category_enum = Category(result.category) if isinstance(result.category, str) else result.category

        db_result = DiagnosticResultDB(
            run_id=result.run_id,
            stage=result.stage,
            category=category_enum,
            root_cause=result.root_cause,
            confidence=result.confidence,
            result_status=result.result_status,
            key_evidence=result.key_evidence,
            next_action=result.next_action,
        )
        self.session.add(db_result)

    async def get_result(self, run_id: str) -> Optional[DiagnosticResult]:
        """获取诊断结果。"""
        stmt = select(DiagnosticResultDB).where(DiagnosticResultDB.run_id == run_id)
        result = await self.session.execute(stmt)
        db_result = result.scalar_one_or_none()

        if not db_result:
            return None

        # 将 Category 枚举转换为字符串值
        category_str = db_result.category.value if hasattr(db_result.category, 'value') else db_result.category

        return DiagnosticResult(
            run_id=db_result.run_id,
            stage=db_result.stage,
            category=category_str,
            root_cause=db_result.root_cause,
            confidence=db_result.confidence,
            result_status=db_result.result_status,
            key_evidence=db_result.key_evidence,
            next_action=db_result.next_action,
            generated_at=db_result.generated_at,
        )
