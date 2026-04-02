"""Web 页面路由."""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional

from chaosdroid.models import RunStatus
from chaosdroid.services import (
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
        _templates = Jinja2Templates(directory="chaosdroid/api/templates")
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
    from chaosdroid.services import ScenarioFilters

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
    from chaosdroid.services import RunFilters

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
    from chaosdroid.models import get_session_context, Device

    with get_session_context() as session:
        devices = session.query(Device).all()

    return _get_templates().TemplateResponse(
        "devices/list.html",
        {
            "request": request,
            "devices": devices,
        }
    )


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
