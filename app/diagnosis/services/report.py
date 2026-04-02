"""报告生成服务 - 异步版本。"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.diagnosis.models import (
    DiagnosticRun,
    RawArtifact,
    NormalizedEventDB,
    DiagnosticResultDB,
    RuleHit,
)
from app.diagnosis.schemas import DiagnosticResult, ReportPayload, NormalizedEvent, SimilarCase
from app.diagnosis.services.similar import SimilarCaseService


class ReportService:
    """报告生成服务。"""

    def __init__(self, session: AsyncSession):
        """初始化服务。"""
        self.session = session
        self.similar_service = SimilarCaseService(session)

        # 初始化 Jinja2 环境
        template_dir = Path(__file__).parent.parent / "web" / "templates"
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        # 注册自定义过滤器
        self.jinja_env.filters["percent"] = lambda value: f"{value:.0%}"

    async def build_payload(self, run_id: str) -> Optional[ReportPayload]:
        """
        构建报告数据结构。

        Args:
            run_id: 任务 ID

        Returns:
            报告数据结构
        """
        # 获取任务信息
        stmt = select(DiagnosticRun).where(DiagnosticRun.run_id == run_id)
        result = await self.session.execute(stmt)
        run = result.scalar_one_or_none()

        if not run:
            return None

        # 获取证据文件
        stmt = select(RawArtifact).where(RawArtifact.run_id == run_id)
        result = await self.session.execute(stmt)
        artifacts = list(result.scalars().all())

        # 获取事件
        stmt = select(NormalizedEventDB).where(NormalizedEventDB.run_id == run_id)
        result = await self.session.execute(stmt)
        db_events = list(result.scalars().all())

        events = [
            NormalizedEvent(
                id=e.id,
                run_id=e.run_id,
                source_type=e.source_type,
                timestamp=e.timestamp,
                line_no=e.line_no,
                raw_line=e.raw_line,
                stage=e.stage,
                event_type=e.event_type,
                severity=e.severity,
                normalized_code=e.normalized_code,
                message=e.message,
                kv_payload=e.kv_payload,
            )
            for e in db_events
        ]

        # 获取诊断结果
        stmt = select(DiagnosticResultDB).where(DiagnosticResultDB.run_id == run_id)
        result = await self.session.execute(stmt)
        db_result = result.scalar_one_or_none()

        result = None
        similar_cases = []

        if db_result:
            result = DiagnosticResult(
                run_id=db_result.run_id,
                stage=db_result.stage,
                category=db_result.category,
                root_cause=db_result.root_cause,
                confidence=db_result.confidence,
                result_status=db_result.result_status,
                key_evidence=db_result.key_evidence,
                next_action=db_result.next_action,
                generated_at=db_result.generated_at,
            )

            # 查找相似案例
            similar_cases = await self.similar_service.search(result)

        # 获取规则命中
        stmt = select(RuleHit).where(RuleHit.run_id == run_id)
        result = await self.session.execute(stmt)
        rule_hits = list(result.scalars().all())

        return ReportPayload(
            run_id=run.run_id,
            device_serial=run.device_serial,
            test_type=run.test_type,
            build_fingerprint=run.build_fingerprint,
            import_path=run.import_path,
            status=run.status,
            started_at=run.started_at,
            finished_at=run.finished_at,
            result=result,
            artifacts=[{"name": a.file_name, "type": a.source_type.value} for a in artifacts],
            events=events,
            rule_hits=[{"rule_id": h.rule_id, "score": h.score} for h in rule_hits],
            similar_cases=similar_cases,
        )

    def export_markdown(self, run_id: str, output_path: str) -> None:
        """
        导出 Markdown 报告。

        Args:
            run_id: 任务 ID
            output_path: 输出文件路径
        """
        # 同步方法，用于 CLI
        import asyncio
        payload = asyncio.get_event_loop().run_until_complete(self.build_payload(run_id))
        if not payload:
            return

        md_content = self._render_markdown(payload)
        Path(output_path).write_text(md_content, encoding="utf-8")

    def export_html(self, run_id: str, output_path: str) -> None:
        """
        导出 HTML 报告。

        Args:
            run_id: 任务 ID
            output_path: 输出文件路径
        """
        # 同步方法，用于 CLI
        import asyncio
        payload = asyncio.get_event_loop().run_until_complete(self.build_payload(run_id))
        if not payload:
            return

        html_content = self._render_html(payload)
        Path(output_path).write_text(html_content, encoding="utf-8")

    def _render_markdown(self, payload: ReportPayload) -> str:
        """渲染 Markdown 报告。"""
        lines = [
            f"# TraceLens 诊断报告",
            f"",
            f"**任务 ID**: {payload.run_id}",
            f"**生成时间**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
            f"## 基本信息",
            f"",
            f"| 字段 | 值 |",
            f"|------|-----|",
            f"| 设备序列号 | {payload.device_serial or 'N/A'} |",
            f"| 测试类型 | {payload.test_type or 'N/A'} |",
            f"| 状态 | {payload.status.value} |",
            f"| 开始时间 | {payload.started_at.strftime('%Y-%m-%d %H:%M:%S')} |",
            f"",
            f"## 证据文件",
            f"",
        ]

        for artifact in payload.artifacts:
            lines.append(f"- {artifact['name']} ({artifact['type']})")

        if payload.result:
            lines.extend([
                f"",
                f"## 诊断结果",
                f"",
                f"| 字段 | 值 |",
                f"|------|-----|",
                f"| 阶段 | {payload.result.stage.value} |",
                f"| 分类 | {payload.result.category} |",
                f"| 根因 | {payload.result.root_cause} |",
                f"| 置信度 | {payload.result.confidence:.0%} |",
                f"| 状态 | {payload.result.result_status.value} |",
                f"",
                f"### 关键证据",
                f"",
            ])

            for evidence in payload.result.key_evidence:
                lines.append(f"- {evidence}")

            if payload.result.next_action:
                lines.extend([
                    f"",
                    f"### 建议动作",
                    f"",
                    f"{payload.result.next_action}",
                ])

        if payload.similar_cases:
            lines.extend([
                f"",
                f"## 相似案例",
                f"",
            ])

            for case in payload.similar_cases:
                lines.append(f"- **{case.run_id}**: {case.category}/{case.root_cause} (相似度：{case.similarity_score:.0%})")

        lines.extend([
            f"",
            f"---",
            f"*Generated by TraceLens*",
        ])

        return "\n".join(lines)

    def _render_html(self, payload: ReportPayload) -> str:
        """渲染 HTML 报告（使用 Jinja2 模板）。"""
        template = self.jinja_env.get_template("reports/report.html")
        return template.render(
            payload=payload,
            generated_at=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        )
