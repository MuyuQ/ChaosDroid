"""Web页面路由."""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

from chaosdroid.models import RunStatus
from chaosdroid.services import (
    list_scenarios, get_scenario, get_scenario_with_runs,
    list_runs, get_run, get_run_steps, get_run_with_template,
    list_reports, get_report, get_report_content,
    list_fault_profiles, list_validation_profiles, list_recovery_profiles,
)

router = APIRouter()
templates = Jinja2Templates(directory="chaosdroid/api/templates")


# ==================== 首页 ====================

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首页."""
    return templates.TemplateResponse("index.html", {"request": request})


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

    return templates.TemplateResponse(
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

    return templates.TemplateResponse(
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

    return templates.TemplateResponse(
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

    return templates.TemplateResponse(
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

    return templates.TemplateResponse(
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

    return templates.TemplateResponse(
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
    # TODO: 实现设备列表获取
    devices = []

    return templates.TemplateResponse(
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

    return templates.TemplateResponse(
        "profiles/list.html",
        {
            "request": request,
            "fault_profiles": fault_profiles,
            "validation_profiles": validation_profiles,
            "recovery_profiles": recovery_profiles,
        }
    )