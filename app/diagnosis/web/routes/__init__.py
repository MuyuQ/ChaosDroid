"""Web路由模块。"""

from fastapi import APIRouter
from jinja2 import Environment
from pathlib import Path

from app.diagnosis.web.routes.pages import (
    router as pages_router,
    register_page_routes,
    is_htmx_request,
    is_api_request,
    render_error_page,
)
from app.diagnosis.web.routes.api import router as api_router, register_api_routes


def create_pages_router(jinja_env: Environment, template_dir: Path) -> APIRouter:
    """创建页面路由器并注册路由。

    Args:
        jinja_env: Jinja2 Environment 实例
        template_dir: 模板目录路径

    Returns:
        APIRouter: 注册了页面路由的路由器
    """
    register_page_routes(pages_router, jinja_env, template_dir)
    return pages_router


def create_api_router() -> APIRouter:
    """创建API路由器并注册路由。

    Returns:
        APIRouter: 注册了API路由的路由器
    """
    register_api_routes(api_router)
    return api_router


__all__ = [
    "pages_router",
    "api_router",
    "create_pages_router",
    "create_api_router",
    "is_htmx_request",
    "is_api_request",
    "render_error_page",
]