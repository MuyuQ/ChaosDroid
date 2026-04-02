"""诊断服务。"""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.diagnosis.engine import RuleEngine
from app.diagnosis.enums import RunStatus, Category
from app.diagnosis.exceptions import NotFoundError, DiagnosisError
from app.diagnosis.models import DiagnosticRun, DiagnosticResultDB, RuleHit, get_session
from app.diagnosis.schemas import DiagnosticResult
from app.diagnosis.services.parse import ParseService
from app.diagnosis.services.rule import RuleService
from app.diagnosis.services.similar import SimilarCaseService


class DiagnoseService:
    """诊断服务。"""

    def __init__(self, session: Optional[Session] = None):
        """初始化服务。"""
        self.session = session or get_session()
        self.parse_service = ParseService(session)
        # 从数据库加载规则，而非仅从YAML文件
        rule_service = RuleService(session)
        rules = rule_service.load_rules_for_engine()
        self.rule_engine = RuleEngine(rules=rules)
        self.rule_service = rule_service
        self.similar_service = SimilarCaseService(session)

    def diagnose(self, run_id: str) -> Optional[DiagnosticResult]:
        """
        对指定任务执行诊断。

        Args:
            run_id: 任务ID

        Returns:
            诊断结果

        Raises:
            NotFoundError: 任务不存在
            DiagnosisError: 诊断执行失败
        """
        # 获取任务
        run = self.session.query(DiagnosticRun).filter(DiagnosticRun.run_id == run_id).first()
        if not run:
            raise NotFoundError(f"任务不存在: {run_id}", {"run_id": run_id})

        try:
            # 解析事件（如果尚未解析）
            events = self.parse_service.get_events(run_id)
            if not events:
                events = self.parse_service.parse_run(run_id)

            # 执行规则匹配，获取匹配的规则列表
            result, matched_rules = self.rule_engine.evaluate(run_id, events)

            if not result:
                raise DiagnosisError(f"规则引擎未能生成诊断结果", {"run_id": run_id})

            # 保存结果
            self._save_result(result)

            # 保存规则命中记录
            self._save_rule_hits(run_id, matched_rules, events)

            # 索引结果用于相似案例召回
            self.similar_service.index_run(result)

            # 更新任务状态
            run.status = RunStatus.DIAGNOSED
            run.finished_at = datetime.utcnow()
            self.session.commit()

            return result

        except NotFoundError:
            # NotFoundError 直接向上传递
            raise
        except DiagnosisError:
            # DiagnosisError 直接向上传递
            raise
        except Exception as e:
            # 其他异常转换为 DiagnosisError
            raise DiagnosisError(f"诊断执行失败: {str(e)}", {"run_id": run_id, "error": str(e)})

    def _save_rule_hits(
        self,
        run_id: str,
        matched_rules: list,
        events: list,
    ) -> None:
        """
        保存规则命中记录。

        Args:
            run_id: 任务ID
            matched_rules: 匹配的规则列表
            events: 标准化事件列表
        """
        for rule in matched_rules:
            # 收集匹配的事件ID
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

    def _save_result(self, result: DiagnosticResult) -> None:
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

    def get_result(self, run_id: str) -> Optional[DiagnosticResult]:
        """获取诊断结果。"""
        db_result = self.session.query(DiagnosticResultDB).filter(DiagnosticResultDB.run_id == run_id).first()

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