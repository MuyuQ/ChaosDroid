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
    return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="ChaosDroid - Android 故障注入测试与恢复验证平台">
    <title>ChaosDroid 控制台</title>
    <link rel="stylesheet" href="/static/css/style.css">
    <style>
        /* 仪表盘统计卡片样式 */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.5rem;
            margin: 2rem 0;
        }
        .stat-card {
            background: linear-gradient(135deg, var(--primary-color) 0%, #1d4ed8 100%);
            color: white;
            padding: 2rem;
            border-radius: 0.5rem;
            text-align: center;
            box-shadow: 0 4px 6px rgba(37, 99, 235, 0.2);
        }
        .stat-card h3 {
            margin: 0;
            font-size: 2.5rem;
            font-weight: 700;
        }
        .stat-card p {
            margin: 0.5rem 0 0;
            opacity: 0.95;
            font-size: 0.875rem;
        }
        .quick-actions {
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            margin-top: 1rem;
        }
        .hero-section {
            text-align: center;
            padding: 2rem 0;
            margin-bottom: 2rem;
        }
        .hero-section h1 {
            font-size: 2rem;
            margin-bottom: 0.5rem;
        }
        .hero-section p {
            color: var(--text-muted);
            font-size: 1.125rem;
        }
    </style>
</head>
<body>
    <a href="#main-content" class="skip-link">跳转到主内容</a>

    <nav class="navbar" role="navigation" aria-label="主导航">
        <div class="container">
            <a href="/" class="navbar-brand" aria-label="ChaosDroid 首页">
                <strong>ChaosDroid</strong>
            </a>
            <button
                type="button"
                class="navbar-toggle"
                aria-expanded="false"
                aria-controls="navbar-menu"
                aria-label="切换导航菜单"
                onclick="toggleNavbar()">
                ☰
            </button>
            <ul class="navbar-nav" id="navbar-menu" role="menubar">
                <li role="none"><a href="/" role="menuitem">仪表盘</a></li>
                <li role="none"><a href="/devices" role="menuitem">设备管理</a></li>
                <li role="none"><a href="/runs" role="menuitem">任务列表</a></li>
                <li role="none"><a href="/diagnosis" role="menuitem">日志诊断</a></li>
            </ul>
        </div>
    </nav>

    <main id="main-content" class="main-content" role="main" tabindex="-1">
        <div class="container">
            <!-- Hero 区域 -->
            <div class="hero-section">
                <h1>ChaosDroid 控制台</h1>
                <p>Android 故障注入测试与恢复验证平台</p>
            </div>

            <!-- 统计卡片 -->
            <div class="stats-grid">
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

            <!-- 快速操作卡片 -->
            <div class="card">
                <div class="card-header">快速操作</div>
                <div class="quick-actions">
                    <a href="/api/scenarios" class="btn btn-primary">场景 API</a>
                    <a href="/api/runs" class="btn btn-primary">执行 API</a>
                    <a href="/api/reports" class="btn btn-primary">报告 API</a>
                    <a href="/docs" class="btn btn-primary">Swagger 文档</a>
                    <a href="/diagnosis" class="btn btn-primary">日志诊断</a>
                </div>
            </div>

            <!-- 系统状态卡片 -->
            <div class="card">
                <div class="card-header">系统状态</div>
                <p style="color: var(--success-color); font-weight: 500;">✓ 服务运行正常，API 已启用</p>
            </div>
        </div>
    </main>

    <footer role="contentinfo" style="text-align: center; padding: 2rem; color: var(--text-muted); border-top: 1px solid var(--border-color); margin-top: 2rem;">
        <p>ChaosDroid - Android fault injection testing and recovery verification platform</p>
    </footer>

    <script>
        // 移动端导航切换
        function toggleNavbar() {
            var menu = document.getElementById('navbar-menu');
            var toggle = document.querySelector('.navbar-toggle');
            var expanded = toggle.getAttribute('aria-expanded') === 'true';
            toggle.setAttribute('aria-expanded', !expanded);
            menu.classList.toggle('show');
        }
    </script>
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
    scenarios, total = await list_scenarios(filters)

    return _get_templates().TemplateResponse(
        request=request,
        name="scenarios/list.html",
        context={
            "request": request,
            "scenarios": scenarios,
            "filters": filters,
        }
    )


@router.get("/scenarios/{scenario_id}", response_class=HTMLResponse)
async def scenario_detail(request: Request, scenario_id: int):
    """场景详情页面."""
    result = await get_scenario_with_runs(scenario_id)
    if not result:
        raise HTTPException(status_code=404, detail="Scenario not found")

    return _get_templates().TemplateResponse(
        request=request,
        name="scenarios/detail.html",
        context={
            "request": request,
            "scenario": result["scenario"],
            "recent_runs": result["recent_runs"],
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
        scenario_template_id=scenario_id,
        device_serial=device_serial,
    )
    runs, total = await list_runs(filters)

    # 获取场景列表用于筛选
    scenarios, _ = await list_scenarios()

    # 预先加载 report 信息，避免模板懒加载
    runs_data = []
    for run in runs:
        run_dict = {
            "run": run,
            "has_report": bool(run.report),
            "report_id": run.report.id if run.report else None,
        }
        runs_data.append(run_dict)

    return _get_templates().TemplateResponse(
        request=request,
        name="runs/list.html",
        context={
            "request": request,
            "runs_data": runs_data,
            "filters": filters,
            "scenarios": scenarios,
            "status_options": [s.value for s in RunStatus],
        }
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail(request: Request, run_id: int):
    """执行详情页面."""
    result = await get_run_with_template(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Run not found")

    steps = await get_run_steps(run_id)

    return _get_templates().TemplateResponse(
        request=request,
        name="runs/detail.html",
        context={
            "request": request,
            "run": result["run"],
            "template": result["template"],
            "result_summary": result.get("parsed_result_summary"),
            "steps": steps,
        }
    )


# ==================== 报告管理 ====================

@router.get("/reports", response_class=HTMLResponse)
async def reports_list(request: Request, limit: int = 20):
    """报告列表页面."""
    reports, _ = await list_reports(limit=limit)

    return _get_templates().TemplateResponse(
        request=request,
        name="reports/list.html",
        context={
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
        request=request,
        name="reports/view.html",
        context={
            "request": request,
            "report": report,
            "content": content,
        }
    )


# ==================== 设备管理 ====================

@router.get("/devices", response_class=HTMLResponse)
async def devices_list(request: Request):
    """设备列表页面."""
    from app.models.database import get_session_factory
    from app.models.device import Device
    from sqlalchemy import select

    factory = get_session_factory()
    async with factory() as session:
        stmt = select(Device)
        result = await session.execute(stmt)
        devices = result.scalars().all()

    return _get_templates().TemplateResponse(
        request=request,
        name="devices/list.html",
        context={
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
    fault_profiles, _ = await list_fault_profiles()
    validation_profiles, _ = await list_validation_profiles()
    recovery_profiles, _ = await list_recovery_profiles()

    return _get_templates().TemplateResponse(
        request=request,
        name="profiles/list.html",
        context={
            "request": request,
            "fault_profiles": fault_profiles,
            "validation_profiles": validation_profiles,
            "recovery_profiles": recovery_profiles,
        }
    )
