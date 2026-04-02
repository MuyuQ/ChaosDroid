"""页面路由模块。"""

import secrets
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, Form, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment
from sqlalchemy.ext.asyncio import AsyncSession

from app.diagnosis.models import get_session, DiagnosticResultDB, SimilarCaseIndex
from app.diagnosis.services import (
    IngestService,
    DiagnoseService,
    ReportService,
    RuleService,
)
from app.diagnosis.exceptions import NotFoundError
from sqlalchemy import select, func


router = APIRouter()


def is_htmx_request(request: Request) -> bool:
    """检测是否为 HTMX 请求。"""
    return request.headers.get("HX-Request") == "true"


def is_api_request(request: Request) -> bool:
    """检测是否为 API 请求。"""
    return request.url.path.startswith("/api")


def generate_csrf_token(request: Request) -> str:
    """生成 CSRF token 用于表单。"""
    token = request.cookies.get("csrf_token")
    if not token:
        token = secrets.token_hex(32)
    return token


def validate_csrf_token(request: Request, csrf_token_from_form: str = None) -> bool:
    """验证 CSRF token。"""
    csrf_token_from_cookie = request.cookies.get("csrf_token")
    csrf_token = csrf_token_from_form or request.headers.get("X-CSRF-Token")
    if not csrf_token_from_cookie or not csrf_token:
        return False
    return csrf_token_from_cookie == csrf_token


def render_template_with_csrf(
    template_name: str,
    context: dict,
    request: Request,
    jinja_env: Environment,
) -> str:
    """渲染模板并自动添加 CSRF token。"""
    csrf_token = generate_csrf_token(request)
    context["csrf_token"] = csrf_token
    template = jinja_env.get_template(template_name)
    return template.render(**context)


def render_error_page(message: str, error_type: str, status_code: int) -> str:
    """渲染错误页面。"""
    return f'''
    <div class="container mt-4">
        <div class="alert alert-danger">
            <h4 class="alert-heading">{error_type}</h4>
            <p>{message}</p>
            <hr>
            <p class="mb-0">请检查输入或<a href="/">返回首页</a>。</p>
        </div>
    </div>
    '''


# 依赖注入：获取数据库会话
async def get_db() -> AsyncSession:
    """获取数据库会话依赖。"""
    async with get_session() as session:
        yield session


def register_page_routes(router: APIRouter, jinja_env: Environment, template_dir: Path):
    """注册页面路由。"""

    def render_template(template_name: str, context: dict) -> str:
        """渲染模板并返回HTML字符串。"""
        template = jinja_env.get_template(template_name)
        return template.render(**context)

    @router.get("/", response_class=HTMLResponse)
    async def index(request: Request, filter: Optional[str] = None, session: AsyncSession = Depends(get_db)):
        """首页仪表盘。"""
        ingest_service = IngestService(session=session)
        all_runs = await ingest_service.list_runs(limit=50)

        results = {}
        failed_count = 0
        passed_count = 0
        pending_count = 0
        diagnosed_count = 0

        for run in all_runs:
            stmt = select(DiagnosticResultDB).where(DiagnosticResultDB.run_id == run.run_id)
            result = await session.execute(stmt)
            result = result.scalar_one_or_none()
            if result:
                results[run.run_id] = result
                diagnosed_count += 1
                result_status = result.result_status.value if hasattr(result.result_status, 'value') else result.result_status
                if result_status == 'passed':
                    passed_count += 1
                elif result_status == 'failed':
                    failed_count += 1
                else:
                    pending_count += 1

        runs = []
        for run in all_runs:
            result = results.get(run.run_id)

            if filter == 'all' or filter is None:
                runs.append(run)
            elif filter == 'passed' and result and result.result_status.value == 'passed':
                runs.append(run)
            elif filter == 'failed' and result and result.result_status.value == 'failed':
                runs.append(run)
            elif filter == 'pending' and result and result.result_status.value not in ('passed', 'failed'):
                runs.append(run)
            elif filter == 'diagnosed' and result:
                runs.append(run)
            elif filter == 'undiagnosed' and not result:
                runs.append(run)

        runs = runs[:20]

        if is_htmx_request(request):
            html = render_template("dashboard_task_list.html", {
                "request": request,
                "runs": runs,
                "results": results,
            })
            return HTMLResponse(content=html)

        html = render_template("dashboard.html", {
            "request": request,
            "runs": runs,
            "results": results,
            "failed_count": failed_count,
            "passed_count": passed_count,
            "pending_count": pending_count,
            "diagnosed_count": diagnosed_count,
            "total_count": len(all_runs),
            "current_filter": filter or 'all',
        })
        return HTMLResponse(content=html)

    @router.get("/import", response_class=HTMLResponse)
    async def import_page(request: Request):
        """导入页面。"""
        html = render_template_with_csrf("import.html", {"request": request}, request, jinja_env)
        response = HTMLResponse(content=html)
        csrf_token = generate_csrf_token(request)
        response.set_cookie(key="csrf_token", value=csrf_token, httponly=False, samesite="strict")
        return response

    @router.post("/import")
    async def import_upload(
        request: Request,
        session: AsyncSession = Depends(get_db),
        csrf_token: str = Form(None),
        path: str = Form(None),
        device_serial: str = Form(...),
        test_type: Optional[str] = Form(None),
    ):
        """处理导入请求。"""
        if not validate_csrf_token(request, csrf_token):
            if is_htmx_request(request):
                return HTMLResponse(content='<div class="alert alert-danger">CSRF 验证失败</div>', status_code=403)
            return HTMLResponse(content="CSRF 验证失败", status_code=403)

        service = IngestService(session=session)
        metadata = {
            "device_serial": device_serial,
            "test_type": test_type,
        }
        metadata = {k: v for k, v in metadata.items() if v}

        if path:
            run_id = await service.ingest_path(path, metadata)
            if is_htmx_request(request):
                return HTMLResponse(content=f'''
                    <div class="alert alert-success">
                        导入成功！任务ID: <a href="/runs/{run_id}">{run_id}</a>
                    </div>
                    <script>
                        // 使用 HTMX 触发重定向（通过 HX-Redirect header）
                    </script>
                ''', headers={"HX-Redirect": f"/runs/{run_id}"})
            return RedirectResponse(url=f"/runs/{run_id}", status_code=303)

        if is_htmx_request(request):
            return HTMLResponse(content='<div class="alert alert-warning">请提供日志路径</div>')
        return RedirectResponse(url="/import", status_code=303)

    @router.post("/import/upload")
    async def import_files_upload(
        request: Request,
        session: AsyncSession = Depends(get_db),
        csrf_token: str = Form(None),
        files: list[UploadFile] = File(...),
        device_serial: str = Form(...),
        test_type: Optional[str] = Form(None),
    ):
        """处理文件上传导入请求。"""
        if not validate_csrf_token(request, csrf_token):
            if is_htmx_request(request):
                return HTMLResponse(content='<div class="alert alert-danger">CSRF 验证失败</div>', status_code=403)
            return HTMLResponse(content="CSRF 验证失败", status_code=403)

        temp_dir = tempfile.mkdtemp(prefix="tracelens_upload_")

        try:
            for upload_file in files:
                file_path = Path(temp_dir) / Path(upload_file.filename).name
                with open(file_path, "wb") as f:
                    shutil.copyfileobj(upload_file.file, f)

            service = IngestService(session=session)
            metadata = {
                "device_serial": device_serial,
                "test_type": test_type,
            }
            metadata = {k: v for k, v in metadata.items() if v}

            run_id = await service.ingest_path(temp_dir, metadata)
            if is_htmx_request(request):
                return HTMLResponse(content=f'''
                    <div class="alert alert-success">
                        上传导入成功！任务ID: <a href="/runs/{run_id}">{run_id}</a>
                    </div>
                ''', headers={"HX-Redirect": f"/runs/{run_id}"})
            return RedirectResponse(url=f"/runs/{run_id}", status_code=303)

        except Exception as e:
            if is_htmx_request(request):
                return HTMLResponse(content=f'<div class="alert alert-danger">导入失败: {str(e)}</div>')
            return RedirectResponse(url="/import", status_code=303)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @router.get("/runs", response_class=HTMLResponse)
    async def runs_list(request: Request, session: AsyncSession = Depends(get_db)):
        """任务列表页面。"""
        ingest_service = IngestService(session=session)
        runs = await ingest_service.list_runs(limit=100)

        results = {}
        for run in runs:
            stmt = select(DiagnosticResultDB).where(DiagnosticResultDB.run_id == run.run_id)
            result = await session.execute(stmt)
            result = result.scalar_one_or_none()
            if result:
                results[run.run_id] = result

        html = render_template("runs/list.html", {
            "request": request,
            "runs": runs,
            "results": results
        })
        return HTMLResponse(content=html)

    @router.get("/runs/{run_id}", response_class=HTMLResponse)
    async def run_detail(request: Request, run_id: str, session: AsyncSession = Depends(get_db)):
        """任务详情页面。"""
        ingest_service = IngestService(session=session)
        run = await ingest_service.get_run(run_id)  # NotFoundError 由服务层抛出，全局处理器捕获

        artifacts = await ingest_service.get_artifacts(run_id)

        report_service = ReportService(session=session)
        payload = await report_service.build_payload(run_id)

        html = render_template_with_csrf(
            "runs/detail.html",
            {"request": request, "run": run, "artifacts": artifacts, "payload": payload},
            request,
            jinja_env,
        )
        response = HTMLResponse(content=html)
        csrf_token = generate_csrf_token(request)
        response.set_cookie(key="csrf_token", value=csrf_token, httponly=False, samesite="strict")
        return response

    @router.post("/runs/{run_id}/diagnose")
    async def run_diagnose(
        request: Request,
        run_id: str,
        session: AsyncSession = Depends(get_db),
        csrf_token: str = Form(...),
    ):
        """执行诊断。"""
        if not validate_csrf_token(request, csrf_token):
            return HTMLResponse(content="CSRF 验证失败", status_code=403)

        service = DiagnoseService(session=session)
        await service.diagnose(run_id)
        return RedirectResponse(url=f"/runs/{run_id}", status_code=303)

    @router.get("/runs/{run_id}/report", response_class=HTMLResponse)
    async def run_report(request: Request, run_id: str, session: AsyncSession = Depends(get_db)):
        """报告详情页面。"""
        service = ReportService(session=session)
        payload = await service.build_payload(run_id)
        if not payload:
            raise NotFoundError(f"报告不存在: {run_id}", {"run_id": run_id})

        html = render_template("reports/detail.html", {"request": request, "payload": payload})
        return HTMLResponse(content=html)

    @router.get("/cases", response_class=HTMLResponse)
    async def cases_page(
        request: Request,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        root_cause: Optional[str] = None,
        session: AsyncSession = Depends(get_db),
    ):
        """案例检索页面。"""
        from rapidfuzz import fuzz

        stmt = select(SimilarCaseIndex)

        if category:
            stmt = stmt.where(SimilarCaseIndex.category == category)
        if root_cause:
            stmt = stmt.where(SimilarCaseIndex.root_cause == root_cause)

        result = await session.execute(stmt.order_by(SimilarCaseIndex.updated_at.desc()))
        all_cases = result.scalars().all()

        if keyword:
            filtered_cases = []
            for case in all_cases:
                score = fuzz.partial_ratio(keyword.lower(), case.feature_text.lower())
                if score > 50:
                    filtered_cases.append(case)
            cases = filtered_cases
        else:
            cases = all_cases

        total_cases_stmt = select(func.count()).select_from(SimilarCaseIndex)
        total_cases_result = await session.execute(total_cases_stmt)
        total_cases = total_cases_result.scalar()

        categories_stmt = select(SimilarCaseIndex.category).distinct()
        categories_result = await session.execute(categories_stmt)
        categories = [c[0] for c in categories_result.all()]

        root_causes_stmt = select(SimilarCaseIndex.root_cause).distinct()
        root_causes_result = await session.execute(root_causes_stmt)
        root_causes = [c[0] for c in root_causes_result.all()]

        html = render_template("cases/search.html", {
            "request": request,
            "cases": cases,
            "keyword": keyword,
            "category": category,
            "root_cause": root_cause,
            "total_cases": total_cases,
            "categories": categories,
            "root_causes": root_causes,
            "filtered_count": len(cases),
        })
        return HTMLResponse(content=html)

    @router.get("/api-docs", response_class=HTMLResponse)
    async def api_docs_page(request: Request):
        """API文档页面。"""
        html = render_template("api_docs.html", {"request": request})
        return HTMLResponse(content=html)

    @router.get("/rules", response_class=HTMLResponse)
    async def rules_list(request: Request, session: AsyncSession = Depends(get_db)):
        """规则列表页面。"""
        service = RuleService(session=session)
        rules = await service.list_rules()
        html = render_template_with_csrf("rules/list.html", {
            "request": request,
            "rules": rules,
        }, request, jinja_env)
        response = HTMLResponse(content=html)
        csrf_token = generate_csrf_token(request)
        response.set_cookie(key="csrf_token", value=csrf_token, httponly=False, samesite="strict")
        return response

    @router.get("/rules/new", response_class=HTMLResponse)
    async def rule_new(request: Request):
        """新增规则页面。"""
        html = render_template_with_csrf("rules/form.html", {
            "request": request,
            "rule": None,
        }, request, jinja_env)
        response = HTMLResponse(content=html)
        csrf_token = generate_csrf_token(request)
        response.set_cookie(key="csrf_token", value=csrf_token, httponly=False, samesite="strict")
        return response

    @router.post("/rules")
    async def rule_create(
        request: Request,
        session: AsyncSession = Depends(get_db),
        csrf_token: str = Form(...),
        rule_id: str = Form(...),
        name: str = Form(...),
        priority: int = Form(50),
        enabled: bool = Form(True),
        match_all: str = Form(""),
        match_any: str = Form(""),
        exclude_any: str = Form(""),
        match_stage: list[str] = Form([]),
        category: str = Form(...),
        root_cause: str = Form(""),
        base_confidence: float = Form(0.9),
        next_action: str = Form(""),
    ):
        """创建新规则。"""
        if not validate_csrf_token(request, csrf_token):
            return HTMLResponse(content="CSRF 验证失败", status_code=403)

        service = RuleService(session=session)
        data = {
            "rule_id": rule_id,
            "name": name,
            "priority": priority,
            "enabled": enabled,
            "match_all": [x.strip() for x in match_all.split("\n") if x.strip()],
            "match_any": [x.strip() for x in match_any.split("\n") if x.strip()],
            "exclude_any": [x.strip() for x in exclude_any.split("\n") if x.strip()],
            "match_stage": match_stage,
            "category": category,
            "root_cause": root_cause or None,
            "base_confidence": base_confidence,
            "next_action": next_action or None,
        }
        await service.create_rule(data)
        return RedirectResponse(url="/rules", status_code=303)

    @router.get("/rules/{rule_id}/edit", response_class=HTMLResponse)
    async def rule_edit(request: Request, rule_id: str, session: AsyncSession = Depends(get_db)):
        """编辑规则页面。"""
        service = RuleService(session=session)
        rule = await service.get_rule(rule_id)
        if not rule:
            raise NotFoundError(f"规则不存在: {rule_id}", {"rule_id": rule_id})

        html = render_template_with_csrf("rules/form.html", {
            "request": request,
            "rule": rule,
        }, request, jinja_env)
        response = HTMLResponse(content=html)
        csrf_token = generate_csrf_token(request)
        response.set_cookie(key="csrf_token", value=csrf_token, httponly=False, samesite="strict")
        return response

    @router.post("/rules/{rule_id}")
    async def rule_update(
        request: Request,
        session: AsyncSession = Depends(get_db),
        rule_id: str = Form(...),
        csrf_token: str = Form(...),
        name: str = Form(...),
        priority: int = Form(50),
        enabled: bool = Form(False),
        match_all: str = Form(""),
        match_any: str = Form(""),
        exclude_any: str = Form(""),
        match_stage: list[str] = Form([]),
        category: str = Form(...),
        root_cause: str = Form(""),
        base_confidence: float = Form(0.9),
        next_action: str = Form(""),
    ):
        """更新规则。"""
        if not validate_csrf_token(request, csrf_token):
            return HTMLResponse(content="CSRF 验证失败", status_code=403)

        service = RuleService(session=session)
        data = {
            "name": name,
            "priority": priority,
            "enabled": enabled,
            "match_all": [x.strip() for x in match_all.split("\n") if x.strip()],
            "match_any": [x.strip() for x in match_any.split("\n") if x.strip()],
            "exclude_any": [x.strip() for x in exclude_any.split("\n") if x.strip()],
            "match_stage": match_stage,
            "category": category,
            "root_cause": root_cause or None,
            "base_confidence": base_confidence,
            "next_action": next_action or None,
        }
        await service.update_rule(rule_id, data)
        return RedirectResponse(url="/rules", status_code=303)

    @router.post("/rules/{rule_id}/delete")
    @router.delete("/rules/{rule_id}/delete")
    async def rule_delete(
        request: Request,
        session: AsyncSession = Depends(get_db),
        rule_id: str = Form(...),
        csrf_token: str = Form(None),
    ):
        """删除规则。"""
        if not validate_csrf_token(request, csrf_token):
            if is_htmx_request(request):
                return HTMLResponse(content='<div class="alert alert-danger">CSRF 验证失败</div>', status_code=403)
            return HTMLResponse(content="CSRF 验证失败", status_code=403)

        service = RuleService(session=session)
        await service.delete_rule(rule_id)

        if is_htmx_request(request):
            rules = await service.list_rules()
            html = render_template("rules/table_body.html", {
                "request": request,
                "rules": rules,
            })
            return HTMLResponse(content=html)

        return RedirectResponse(url="/rules", status_code=303)