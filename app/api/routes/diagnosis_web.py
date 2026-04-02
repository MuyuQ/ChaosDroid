"""诊断 Web 页面路由。"""

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.diagnosis.services.ingest import IngestService
from app.diagnosis.services.diagnose import DiagnoseService
from app.diagnosis.models.db import get_session
from app.diagnosis.exceptions import NotFoundError, DiagnosisError


router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="app/api/templates")


@router.get("/diagnosis", response_class=HTMLResponse)
async def diagnosis_list(request: Request):
    """诊断列表页面。"""
    session = get_session()
    ingest_service = IngestService()
    runs = ingest_service.list_runs(limit=50)

    # 获取每个任务的诊断结果
    diagnose_service = DiagnoseService(session=session)
    results = {}
    for run in runs:
        try:
            result = diagnose_service.get_result(run.run_id)
            if result:
                results[run.run_id] = result
        except Exception:
            pass

    # 获取 CSRF token
    csrf_token = request.cookies.get("csrf_token")
    if not csrf_token:
        import secrets
        csrf_token = secrets.token_hex(32)

    return templates.TemplateResponse("diagnosis/list.html", {
        "request": request,
        "runs": runs,
        "results": results,
        "csrf_token": csrf_token,
    })


@router.get("/diagnosis/{run_id}", response_class=HTMLResponse)
async def diagnosis_detail(request: Request, run_id: str):
    """诊断详情页面。"""
    session = get_session()
    ingest_service = IngestService()

    try:
        run = ingest_service.get_run(run_id)
    except Exception:
        raise HTTPException(status_code=404, detail="任务不存在")

    diagnose_service = DiagnoseService(session=session)
    result = diagnose_service.get_result(run_id)

    # 获取 CSRF token
    csrf_token = request.cookies.get("csrf_token")
    if not csrf_token:
        import secrets
        csrf_token = secrets.token_hex(32)

    return templates.TemplateResponse("diagnosis/detail.html", {
        "request": request,
        "run": run,
        "result": result,
        "csrf_token": csrf_token,
    })


@router.post("/diagnosis/{run_id}/execute")
async def diagnosis_execute(request: Request, run_id: str, csrf_token: str = Form(...)):
    """执行诊断。"""
    # CSRF 验证
    csrf_cookie = request.cookies.get("csrf_token")
    if csrf_cookie != csrf_token:
        return HTMLResponse(content="CSRF 验证失败", status_code=403)

    session = get_session()
    service = DiagnoseService(session=session)

    try:
        service.diagnose(run_id)
    except NotFoundError as e:
        return HTMLResponse(content=f"诊断失败：{str(e)}", status_code=404)
    except DiagnosisError as e:
        return HTMLResponse(content=f"诊断失败：{str(e)}", status_code=500)

    return RedirectResponse(url=f"/diagnosis/{run_id}", status_code=303)
