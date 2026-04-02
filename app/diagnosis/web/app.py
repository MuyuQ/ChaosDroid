"""FastAPI Web应用。"""

import secrets
from pathlib import Path

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from fastapi_csrf_protect import CsrfProtect
from fastapi_csrf_protect.exceptions import CsrfProtectError

from app.diagnosis.models import init_db, get_session
from app.diagnosis.exceptions import TraceLensError, get_status_code
from app.diagnosis.web.csrf import csrf_protect
from app.diagnosis.web.routes import (
    create_pages_router,
    create_api_router,
    is_htmx_request,
    is_api_request,
    render_error_page,
)


def create_app() -> FastAPI:
    """创建FastAPI应用实例。"""
    init_db()

    app = FastAPI(
        title="TraceLens",
        description="Android upgrade/stability testing diagnostic workbench",
        version="0.1.0",
    )

    # 模板目录
    template_dir = Path(__file__).parent / "templates"

    # 使用 Jinja2 Environment
    jinja_env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )

    # 注册 CSRF 保护异常处理器
    @app.exception_handler(CsrfProtectError)
    def csrf_protect_error_handler(request: Request, exc: CsrfProtectError):
        return HTMLResponse(
            content=f"<h1>CSRF 验证失败</h1><p>{exc.message}</p>",
            status_code=exc.status_code,
        )

    # 注册 TraceLens 异常处理器
    @app.exception_handler(TraceLensError)
    def tracelens_error_handler(request: Request, exc: TraceLensError):
        """统一处理 TraceLens 业务异常。"""
        status_code = get_status_code(exc)

        # API 请求返回 JSON
        if is_api_request(request):
            return JSONResponse(
                status_code=status_code,
                content=exc.to_dict(),
            )

        # HTMX 请求返回 HTML 片段
        if is_htmx_request(request):
            return HTMLResponse(
                content=f'<div class="alert alert-danger">{exc.message}</div>',
                status_code=status_code,
            )

        # 普通页面请求返回完整错误页面
        return HTMLResponse(
            content=render_error_page(exc.message, exc.__class__.__name__, status_code),
            status_code=status_code,
        )

    # 依赖注入
    def get_db():
        db = get_session()
        try:
            yield db
        finally:
            db.close()

    # CSRF token 获取端点
    @app.get("/csrf-token")
    async def get_csrf_token(request: Request, csrf: CsrfProtect = Depends(csrf_protect)):
        """获取 CSRF token。"""
        response = JSONResponse(status_code=200, content={"csrf_token": "set"})
        token = secrets.token_hex(32)
        response.set_cookie(key="csrf_token", value=token, httponly=False, samesite="strict")
        return response

    # 注册页面路由
    pages_router = create_pages_router(jinja_env, template_dir)
    app.include_router(pages_router)

    # 注册API路由
    api_router = create_api_router()
    app.include_router(api_router)

    return app