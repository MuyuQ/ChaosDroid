"""FastAPI 应用入口。"""

import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes import scenarios, runs, reports, devices, profiles, web, pools, diagnosis, diagnosis_web
from app.config.settings import get_settings
from app.models.database import init_engine, create_tables


CSRF_TOKEN_COOKIE = "csrf_token"
CSRF_TOKEN_LENGTH = 32

# 不需要 API Key 认证的路径
PUBLIC_PATHS = [
    "/",
    "/health",
]
# 不需要 API Key 认证的路径前缀
PUBLIC_PATH_PREFIXES = [
    "/static",
    "/devices",
    "/runs",
    "/pools",
    "/scenarios",
    "/reports",
    "/diagnosis",
]
# 需要 API Key 认证的路径前缀
API_PATH_PREFIX = "/api"


class CSRFMiddleware(BaseHTTPMiddleware):
    """CSRF 保护中间件。"""

    async def dispatch(self, request: Request, call_next):
        csrf_token = request.cookies.get(CSRF_TOKEN_COOKIE)

        if not csrf_token:
            csrf_token = secrets.token_urlsafe(CSRF_TOKEN_LENGTH)

        if request.method in ("POST", "PUT", "DELETE"):
            header_token = request.headers.get("X-CSRF-Token")

            if header_token is not None:
                cookie_token = request.cookies.get(CSRF_TOKEN_COOKIE)
                if not cookie_token or cookie_token != header_token:
                    return JSONResponse(
                        {"detail": "CSRF token missing or invalid"},
                        status_code=400
                    )

        response = await call_next(request)

        if not request.cookies.get(CSRF_TOKEN_COOKIE):
            response.set_cookie(
                key=CSRF_TOKEN_COOKIE,
                value=csrf_token,
                httponly=False,
                samesite="strict",
                max_age=86400 * 30,
            )

        return response


class APIKeyMiddleware(BaseHTTPMiddleware):
    """API Key 认证中间件。"""

    def __init__(self, app, api_keys: list[str], header_name: str = "X-API-Key"):
        super().__init__(app)
        self.api_keys = set(api_keys)
        self.header_name = header_name

    def _is_public_path(self, path: str) -> bool:
        if path in PUBLIC_PATHS:
            return True
        for prefix in PUBLIC_PATH_PREFIXES:
            if path.startswith(prefix):
                return True
        return False

    def _is_api_path(self, path: str) -> bool:
        return path.startswith(API_PATH_PREFIX)

    async def dispatch(self, request: Request, call_next):
        if self._is_public_path(request.url.path):
            return await call_next(request)

        if self._is_api_path(request.url.path):
            settings = get_settings()
            if not settings.api_keys:
                return await call_next(request)

            api_key = request.headers.get(self.header_name)

            if not api_key or api_key not in self.api_keys:
                return JSONResponse(
                    {"detail": "Invalid or missing API key"},
                    status_code=401,
                    headers={"WWW-Authenticate": f"ApiKey header={self.header_name}"}
                )

        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    settings = get_settings()
    init_engine(settings.database_path)
    await create_tables()
    yield


app = FastAPI(
    title="ChaosDroid",
    description="Android fault injection testing and recovery verification platform",
    version="0.1.0",
    lifespan=lifespan,
)

# 添加 CSRF 中间件
app.add_middleware(CSRFMiddleware)

# 添加 API Key 中间件
settings = get_settings()
if settings.api_keys:
    app.add_middleware(
        APIKeyMiddleware,
        api_keys=settings.api_keys,
        header_name="X-API-Key",
    )

# 静态文件挂载
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 模板配置
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# 注册路由
app.include_router(web.router, tags=["web"])
app.include_router(devices.router)
app.include_router(runs.router)
app.include_router(reports.router)
app.include_router(scenarios.router)
app.include_router(profiles.router)
app.include_router(pools.router)
app.include_router(diagnosis.router)
app.include_router(diagnosis_web.router)


@app.get("/health")
async def health_check():
    """健康检查端点。"""
    return {"status": "healthy"}
