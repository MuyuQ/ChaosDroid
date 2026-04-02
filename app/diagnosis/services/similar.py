"""相似案例召回服务。"""

from typing import Optional

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.diagnosis.config import settings
from app.diagnosis.models import SimilarCaseIndex, CaseLink, DiagnosticResultDB, get_session
from app.diagnosis.schemas import DiagnosticResult, SimilarCase


class SimilarCaseService:
    """相似案例召回服务。"""

    def __init__(self, session: Optional[Session] = None):
        """初始化服务。"""
        self.session = session or get_session()

    def search(self, result: DiagnosticResult, limit: int = 3) -> list[SimilarCase]:
        """
        从历史案例中召回相似案例。

        Args:
            result: 当前诊断结果
            limit: 返回数量限制

        Returns:
            相似案例列表
        """
        # 构建特征文本
        feature_text = self._build_feature_text(result)

        # 查询历史案例索引
        candidates = self.session.query(SimilarCaseIndex).filter(
            SimilarCaseIndex.run_id != result.run_id
        ).all()

        # 计算相似度
        scored_cases = []
        for candidate in candidates:
            score = self._calculate_similarity(
                feature_text,
                result.root_cause,
                candidate,
            )
            if score > settings.similarity_threshold:
                scored_cases.append((candidate, score))

        # 排序并取top N
        scored_cases.sort(key=lambda x: x[1], reverse=True)
        top_cases = scored_cases[:limit]

        # 转换为SimilarCase对象
        similar_cases = []
        for candidate, score in top_cases:
            similar_case = SimilarCase(
                run_id=candidate.run_id,
                category=candidate.category,
                root_cause=candidate.root_cause,
                similarity_score=score,
                reason=f"相似特征: {candidate.category}/{candidate.root_cause}",
            )
            similar_cases.append(similar_case)

            # 保存关联记录（不立即提交，让调用者控制事务边界）
            self._save_case_link(result.run_id, candidate.run_id, score)

        # 不在此处提交，让调用者控制事务边界
        return similar_cases

    def _build_feature_text(self, result: DiagnosticResult) -> str:
        """构建特征文本。"""
        parts = [
            result.category,
            result.root_cause or "",
            result.stage.value,
        ]
        return " ".join(parts)

    def _calculate_similarity(
        self,
        feature_text: str,
        root_cause: str,
        candidate: SimilarCaseIndex,
    ) -> float:
        """
        计算相似度。

        使用多种方法综合评估：
        1. 根因完全匹配
        2. 特征文本相似度
        3. 代码签名相似度
        """
        score = 0.0

        # 根因完全匹配
        if root_cause == candidate.root_cause:
            score += settings.similarity_root_cause_weight

        # 分类匹配
        if feature_text.split()[0] == candidate.category:
            score += settings.similarity_category_weight

        # 特征文本相似度
        text_similarity = fuzz.ratio(feature_text, candidate.feature_text) / 100.0
        score += text_similarity * settings.similarity_text_weight

        return min(1.0, score)

    def _save_case_link(self, run_id: str, similar_run_id: str, score: float) -> None:
        """保存案例关联记录。"""
        link = CaseLink(
            run_id=run_id,
            similar_run_id=similar_run_id,
            similarity_score=score,
            reason="automatic_similarity_detection",
        )
        self.session.add(link)

    def index_run(self, result: DiagnosticResult) -> None:
        """
        将诊断结果索引到相似案例库。

        Args:
            result: 诊断结果
        """
        feature_text = self._build_feature_text(result)

        # 检查是否已存在
        existing = self.session.query(SimilarCaseIndex).filter(
            SimilarCaseIndex.run_id == result.run_id
        ).first()

        if existing:
            existing.category = result.category
            existing.root_cause = result.root_cause
            existing.feature_text = feature_text
            existing.normalized_code_signature = result.key_evidence
        else:
            index = SimilarCaseIndex(
                run_id=result.run_id,
                category=result.category,
                root_cause=result.root_cause,
                feature_text=feature_text,
                normalized_code_signature=result.key_evidence,
            )
            self.session.add(index)

        # 不在此处提交，让调用者控制事务边界

    def rebuild_index(self) -> int:
        """
        重建相似案例索引。

        Returns:
            索引数量
        """
        # 清空现有索引
        self.session.query(SimilarCaseIndex).delete()

        # 获取所有诊断结果
        results = self.session.query(DiagnosticResultDB).all()

        count = 0
        for db_result in results:
            result = DiagnosticResult(
                run_id=db_result.run_id,
                stage=db_result.stage,
                category=db_result.category,
                root_cause=db_result.root_cause,
                confidence=db_result.confidence,
                result_status=db_result.result_status,
                key_evidence=db_result.key_evidence,
            )
            self.index_run(result)
            count += 1

        # 提交所有索引变更
        self.session.commit()
        return count