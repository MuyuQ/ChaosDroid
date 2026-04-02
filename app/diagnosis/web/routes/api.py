"""API路由模块。"""

import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app.diagnosis.models import get_session, SimilarCaseIndex
from app.diagnosis.services import IngestService, DiagnoseService, ReportService, RuleService, SimilarCaseService
from app.diagnosis.exceptions import NotFoundError


router = APIRouter(prefix="/api")


def register_api_routes(router: APIRouter):
    """注册API路由。"""

    @router.post("/runs/import")
    async def api_import(request: Request):
        """API: 导入日志。"""
        data = await request.json()
        service = IngestService()
        run_id = service.ingest_path(data.get("path"), data.get("metadata"))
        return {"run_id": run_id}

    @router.get("/runs")
    async def api_runs():
        """API: 任务列表。"""
        service = IngestService()
        runs = service.list_runs()
        return [{"run_id": r.run_id, "status": r.status.value} for r in runs]

    @router.get("/runs/{run_id}")
    async def api_run(run_id: str):
        """API: 任务详情。"""
        service = ReportService()
        payload = service.build_payload(run_id)
        if not payload:
            raise NotFoundError(f"任务不存在: {run_id}", {"run_id": run_id})
        return payload.model_dump()

    @router.post("/runs/{run_id}/diagnose")
    async def api_diagnose(run_id: str):
        """API: 执行诊断。"""
        service = DiagnoseService()
        result = service.diagnose(run_id)  # NotFoundError/DiagnosisError 由服务层抛出
        return result.model_dump()

    @router.get("/runs/{run_id}/report")
    async def api_report(run_id: str):
        """API: 获取报告。"""
        service = ReportService()
        payload = service.build_payload(run_id)
        if not payload:
            raise NotFoundError(f"报告不存在: {run_id}", {"run_id": run_id})
        return payload.model_dump()

    @router.get("/cases")
    async def api_cases():
        """API: 案例列表。"""
        session = get_session()
        cases = session.query(SimilarCaseIndex).all()
        return [{
            "run_id": c.run_id,
            "category": c.category,
            "root_cause": c.root_cause,
            "feature_text": c.feature_text,
            "updated_at": c.updated_at.isoformat(),
        } for c in cases]

    @router.post("/cases/rebuild")
    async def api_cases_rebuild():
        """API: 重建案例索引。"""
        service = SimilarCaseService()
        count = service.rebuild_index()
        return {"indexed_count": count, "message": "索引重建完成"}

    @router.get("/cases/search")
    async def api_cases_search(
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        root_cause: Optional[str] = None,
        limit: int = 10,
    ):
        """API: 搜索相似案例。"""
        from rapidfuzz import fuzz

        session = get_session()

        query = session.query(SimilarCaseIndex)
        if category:
            query = query.filter(SimilarCaseIndex.category == category)
        if root_cause:
            query = query.filter(SimilarCaseIndex.root_cause == root_cause)

        cases = query.limit(limit).all()

        if keyword:
            scored = []
            for case in cases:
                score = fuzz.partial_ratio(keyword.lower(), case.feature_text.lower())
                if score > 50:
                    scored.append((case, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            cases = [c[0] for c in scored[:limit]]

        return [{
            "run_id": c.run_id,
            "category": c.category,
            "root_cause": c.root_cause,
            "feature_text": c.feature_text,
            "updated_at": c.updated_at.isoformat(),
        } for c in cases]

    @router.get("/rules")
    async def api_rules():
        """API: 规则列表。"""
        service = RuleService()
        rules = service.list_rules()
        return [{
            "rule_id": r.rule_id,
            "name": r.name,
            "priority": r.priority,
            "enabled": r.enabled,
            "category": r.category,
            "root_cause": r.root_cause,
        } for r in rules]

    @router.post("/rules")
    async def api_rule_create(request: Request):
        """API: 创建规则。"""
        data = await request.json()
        service = RuleService()
        rule = service.create_rule(data)
        return {"rule_id": rule.rule_id, "message": "规则创建成功"}

    @router.get("/rules/export")
    async def api_rules_export():
        """API: 导出规则到YAML。"""
        service = RuleService()

        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8')
        temp_file.close()

        service.export_to_yaml(Path(temp_file.name))
        return FileResponse(
            path=temp_file.name,
            filename="rules_export.yaml",
            media_type="application/x-yaml"
        )

    @router.post("/rules/import")
    async def api_rules_import(request: Request):
        """API: 从YAML导入规则。"""
        data = await request.json()
        file_path = Path(data.get("file_path", "core_rules.yaml"))
        service = RuleService()
        count = service.import_from_yaml(file_path)
        return {"imported_count": count, "message": "规则导入完成"}