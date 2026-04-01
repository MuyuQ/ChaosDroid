"""API main application."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from chaosdroid.api.routes import scenarios, runs, reports, devices, profiles, web, pools
from chaosdroid.config.settings import get_settings
from chaosdroid.models.database import init_engine, create_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    settings = get_settings()
    init_engine(settings.database_path)
    await create_tables()
    yield
    # 关闭时清理资源


def create_app() -> FastAPI:
    """创建FastAPI应用"""
    app = FastAPI(
        title="ChaosDroid",
        description="Android fault injection testing and recovery verification platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # 注册API路由
    app.include_router(scenarios.router, prefix="/api/scenarios", tags=["scenarios"])
    app.include_router(runs.router, prefix="/api/runs", tags=["runs"])
    app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
    app.include_router(devices.router, prefix="/api/devices", tags=["devices"])
    app.include_router(profiles.router, prefix="/api/profiles", tags=["profiles"])
    app.include_router(pools.router, prefix="/api/pools", tags=["pools"])

    # 注册Web页面路由
    app.include_router(web.router, tags=["web"])

    # 静态文件
    static_dir = Path("chaosdroid/api/static")
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return app


app = create_app()