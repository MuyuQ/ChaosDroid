"""API main application."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from chaosdroid.api.routes import scenarios, runs, reports, devices
from chaosdroid.config.settings import settings
from chaosdroid.models.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    await init_db()
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

    # 模板和静态文件
    # templates = Jinja2Templates(directory="chaosdroid/api/templates")
    # app.mount("/static", StaticFiles(directory="chaosdroid/api/static"), name="static")

    return app


app = create_app()