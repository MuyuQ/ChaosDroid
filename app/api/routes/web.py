"""Web 页面路由."""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional

from app.models import RunStatus
from app.services import (
    list_scenarios, get_scenario, get_scenario_with_runs,
    list_runs, get_run, get_run_steps, get_run_with_template,
    list_reports, get_report, get_report_content,
    list_fault_profiles, list_validation_profiles, list_recovery_profiles,
)

router = APIRouter()

# 延迟导入 templates，避免循环导入
_templates = None

def _get_templates():
    global _templates
    if _templates is None:
        from starlette.templating import Jinja2Templates
        from pathlib import Path
        import jinja2
        template_dir = Path(__file__).parent.parent / "templates"
        # 创建不带缓存的 Jinja2 环境
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(template_dir)),
            autoescape=True,
            cache_size=0,  # 禁用缓存
        )
        _templates = Jinja2Templates(env=env)
    return _templates


# ==================== 健康检查 ====================

@router.get("/health")
async def health_check():
    """健康检查端点，用于负载均衡和监控。

    此端点不需要认证。

    Returns:
        JSONResponse: 健康状态响应
    """
    return JSONResponse(
        status_code=200,
        content={"status": "healthy", "service": "ChaosDroid"}
    )


# ==================== 首页 ====================

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首页."""
    # 直接返回简单 HTML，避免模板缓存问题
    return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ChaosDroid 控制台</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #333; }
        .card { background: white; padding: 20px; border-radius: 8px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; }
        .stat-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; text-align: center; }
        .stat-card h3 { margin: 0; font-size: 2em; }
        .stat-card p { margin: 10px 0 0; opacity: 0.9; }
        a { color: #667eea; }
        .btn { display: inline-block; padding: 10px 20px; background: #667eea; color: white; text-decoration: none; border-radius: 4px; margin: 5px; }
        .btn:hover { background: #5a6fd6; }
    </style>
</head>
<body>
    <div class="container">
        <h1>ChaosDroid 控制台</h1>
        <p>Android 故障注入测试与恢复验证平台</p>

        <div class="stats">
            <div class="stat-card">
                <h3>0</h3>
                <p>场景模板</p>
            </div>
            <div class="stat-card">
                <h3>0</h3>
                <p>执行记录</p>
            </div>
            <div class="stat-card">
                <h3>0</h3>
                <p>测试通过</p>
            </div>
            <div class="stat-card">
                <h3>0</h3>
                <p>测试失败</p>
            </div>
        </div>

        <div class="card">
            <h2>快速操作</h2>
            <a href="/api/scenarios" class="btn">场景 API</a>
            <a href="/api/runs" class="btn">执行 API</a>
            <a href="/api/reports" class="btn">报告 API</a>
            <a href="/docs" class="btn">Swagger 文档</a>
        </div>

        <div class="card">
            <h2>系统状态</h2>
            <p>服务运行正常，API 已启用。</p>
        </div>
    </div>
</body>
</html>
""")


# ==================== 场景管理 ====================

@router.get("/scenarios", response_class=HTMLResponse)
async def scenarios_list(
    request: Request,
    target_type: Optional[str] = None,
    enabled: Optional[bool] = None
):
    """场景列表页面."""
    from app.services import ScenarioFilters

    filters = ScenarioFilters(target_type=target_type, enabled=enabled)
    scenarios = await list_scenarios(filters)

    return _get_templates().TemplateResponse(
        "scenarios/list.html",
        {
            "request": request,
            "scenarios": scenarios,
            "filters": filters,
        }
    )


@router.get("/scenarios/{scenario_id}", response_class=HTMLResponse)
async def scenario_detail(request: Request, scenario_id: int):
    """场景详情页面."""
    scenario = await get_scenario_with_runs(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    return _get_templates().TemplateResponse(
        "scenarios/detail.html",
        {
            "request": request,
            "scenario": scenario,
        }
    )


# ==================== 执行管理 ====================

@router.get("/runs", response_class=HTMLResponse)
async def runs_list(
    request: Request,
    status: Optional[str] = None,
    scenario_id: Optional[int] = None,
    device_serial: Optional[str] = None,
    limit: int = 20
):
    """执行列表页面."""
    from app.services import RunFilters

    filters = RunFilters(
        status=status,
        scenario_id=scenario_id,
        device_serial=device_serial,
        limit=limit
    )
    runs = await list_runs(filters)

    # 获取场景列表用于筛选
    scenarios = await list_scenarios()

    return _get_templates().TemplateResponse(
        "runs/list.html",
        {
            "request": request,
            "runs": runs,
            "filters": filters,
            "scenarios": scenarios,
            "status_options": [s.value for s in RunStatus],
        }
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail(request: Request, run_id: int):
    """执行详情页面."""
    run = await get_run_with_template(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    steps = await get_run_steps(run_id)

    return _get_templates().TemplateResponse(
        "runs/detail.html",
        {
            "request": request,
            "run": run,
            "steps": steps,
        }
    )


# ==================== 报告管理 ====================

@router.get("/reports", response_class=HTMLResponse)
async def reports_list(request: Request, limit: int = 20):
    """报告列表页面."""
    reports = await list_reports(limit=limit)

    return _get_templates().TemplateResponse(
        "reports/list.html",
        {
            "request": request,
            "reports": reports,
        }
    )


@router.get("/reports/{report_id}", response_class=HTMLResponse)
async def report_view(request: Request, report_id: int):
    """报告查看页面."""
    report = await get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # 获取报告内容
    content = await get_report_content(report_id)

    return _get_templates().TemplateResponse(
        "reports/view.html",
        {
            "request": request,
            "report": report,
            "content": content,
        }
    )


# ==================== 设备管理 ====================

@router.get("/devices", response_class=HTMLResponse)
async def devices_list(request: Request):
    """设备列表页面."""
    from app.models import get_session_context, Device

    with get_session_context() as session:
        devices = session.query(Device).all()

    return _get_templates().TemplateResponse(
        "devices/list.html",
        {
            "request": request,
            "devices": devices,
        }
    )


# ==================== 诊断管理 ====================

@router.get("/diagnosis", response_class=HTMLResponse)
async def diagnosis_list(request: Request):
    """诊断列表页面."""
    from app.diagnosis.services.ingest import IngestService
    from app.diagnosis.services.diagnose import DiagnoseService
    from app.diagnosis.models.db import get_async_session_factory

    # 创建会话
    factory = get_async_session_factory()
    async with factory() as session:
        try:
            ingest_service = IngestService(session=session)
            runs = await ingest_service.list_runs(limit=50)

            # 获取每个任务的诊断结果
            diagnose_service = DiagnoseService(session=session)
            results_map = {}  # run_id -> diagnosis result
            for run in runs:
                try:
                    result = await diagnose_service.get_result(run.run_id)
                    if result:
                        # 转换为简单的字典，避免 Jinja2 缓存问题
                        # 确保所有键和值都是简单类型
                        key = str(run.run_id)
                        results_map[key] = {
                            "category": str(result.category),
                            "root_cause": result.root_cause or "",
                            "confidence": float(result.confidence),
                            "result_status": str(result.result_status.value if hasattr(result.result_status, 'value') else result.result_status),
                        }
                except Exception:
                    pass

            await session.commit()
        except Exception:
            await session.rollback()
            raise

    # 获取 CSRF token
    import secrets
    csrf_token = request.cookies.get("csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_hex(32)

    # 构建简单类型的 runs 列表
    runs_data = []
    for run in runs:
        runs_data.append({
            "run_id": str(run.run_id),
            "device_serial": run.device_serial or "-",
            "test_type": run.test_type or "-",
            "status": str(run.status.value if hasattr(run.status, 'value') else run.status),
        })

    return _get_templates().TemplateResponse(
        request=request,
        name="diagnosis/list.html",
        context={
            "runs": runs_data,
            "results_map": results_map,
            "csrf_token": csrf_token,
        },
    )


@router.get("/diagnosis/{run_id}", response_class=HTMLResponse)
async def diagnosis_detail(request: Request, run_id: str):
    """诊断详情页面."""
    from app.diagnosis.services.ingest import IngestService
    from app.diagnosis.services.diagnose import DiagnoseService
    from app.diagnosis.models.db import get_async_session_factory

    # 创建会话
    factory = get_async_session_factory()
    async with factory() as session:
        try:
            ingest_service = IngestService(session=session)

            try:
                run = await ingest_service.get_run(run_id)
            except Exception:
                raise HTTPException(status_code=404, detail="任务不存在")

            diagnose_service = DiagnoseService(session=session)
            result = await diagnose_service.get_result(run_id)

            await session.commit()
        except Exception:
            await session.rollback()
            raise

    # 获取 CSRF token
    import secrets
    csrf_token = request.cookies.get("csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_hex(32)

    return _get_templates().TemplateResponse(
        request=request,
        name="diagnosis/detail.html",
        context={
            "run": run,
            "result": result,
            "csrf_token": csrf_token,
        },
    )


@router.post("/diagnosis/{run_id}/execute", response_class=HTMLResponse)
async def diagnosis_execute(request: Request, run_id: str, csrf_token: str = None):
    """执行诊断."""
    from app.diagnosis.services.diagnose import DiagnoseService
    from app.diagnosis.models.db import get_async_session_factory
    from fastapi.responses import RedirectResponse

    # CSRF 验证
    csrf_cookie = request.cookies.get("csrf_token")
    if csrf_cookie != csrf_token:
        return HTMLResponse(content="CSRF 验证失败", status_code=403)

    # 创建会话
    factory = get_async_session_factory()
    async with factory() as session:
        try:
            service = DiagnoseService(session=session)

            try:
                await service.diagnose(run_id)
                await session.commit()
            except Exception as e:
                await session.rollback()
                return HTMLResponse(content=f"诊断失败：{str(e)}", status_code=500)
        except Exception:
            await session.rollback()
            raise

    return RedirectResponse(url=f"/diagnosis/{run_id}", status_code=303)


# ==================== 配置管理 ====================

@router.get("/profiles", response_class=HTMLResponse)
async def profiles_list(request: Request):
    """配置列表页面."""
    fault_profiles = await list_fault_profiles()
    validation_profiles = await list_validation_profiles()
    recovery_profiles = await list_recovery_profiles()

    return _get_templates().TemplateResponse(
        "profiles/list.html",
        {
            "request": request,
            "fault_profiles": fault_profiles,
            "validation_profiles": validation_profiles,
            "recovery_profiles": recovery_profiles,
        }
    )
