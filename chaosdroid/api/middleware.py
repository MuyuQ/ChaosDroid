"""API 认证中间件模块.

提供 API Key 认证功能，支持 X-API-Key 请求头验证。
"""

import logging
from typing import Any, Callable, Set

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("chaosdroid")


class APIKeyAuthenticationMiddleware(BaseHTTPMiddleware):
    """API Key 认证中间件.

    功能：
    - 验证 X-API-Key 请求头
    - 支持配置免认证端点
    - 支持多个有效 API Key
    - 认证失败返回 401

    Attributes:
        api_keys: 有效的 API Key 集合
        exclude_paths: 免认证的路径集合
    """

    def __init__(
        self,
        app: Any,
        api_keys: Set[str],
        exclude_paths: Set[str],
    ) -> None:
        """初始化中间件.

        Args:
            app: ASGI 应用实例
            api_keys: 有效的 API Key 集合
            exclude_paths: 免认证的路径集合（支持前缀匹配）
        """
        super().__init__(app)
        self.api_keys = api_keys
        self.exclude_paths = exclude_paths

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """处理请求认证.

        Args:
            request: FastAPI 请求对象
            call_next: 下一个处理器

        Returns:
            Response: 响应对象，认证失败时返回 401
        """
        # 未配置 API Key 时跳过认证（开发模式）
        if not self.api_keys:
            logger.debug(f"未配置 API Key，跳过认证：{request.url.path}")
            return await call_next(request)

        # 检查是否需要认证
        if self._is_excluded(request.url.path):
            logger.debug(f"跳过认证：{request.url.path}")
            return await call_next(request)

        # 获取 API Key
        api_key = request.headers.get("X-API-Key")

        # 验证 API Key
        if not api_key or api_key not in self.api_keys:
            logger.warning(
                f"认证失败：{request.method} {request.url.path}, "
                f"API Key: {'missing' if not api_key else 'invalid'}"
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "message": "Invalid or missing API Key",
                },
                headers={"WWW-Authenticate": "API-Key"},
            )

        # 认证通过，添加用户信息到请求状态
        request.state.api_key = api_key
        logger.debug(f"认证通过：{request.method} {request.url.path}")

        return await call_next(request)

    def _is_excluded(self, path: str) -> bool:
        """检查路径是否在免认证列表中.

        支持前缀匹配，例如 /health 排除 /health 和 /health/check

        Args:
            path: 请求路径

        Returns:
            bool: 是否免认证
        """
        # 精确匹配
        if path in self.exclude_paths:
            return True

        # 前缀匹配（支持 /api/health 形式的端点）
        for exclude_path in self.exclude_paths:
            if path.startswith(exclude_path + "/") or path.startswith(exclude_path):
                return True

        return False


def setup_authentication(
    app: FastAPI,
    api_keys: Set[str],
    exclude_paths: Set[str],
) -> None:
    """设置认证中间件.

    Args:
        app: FastAPI 应用实例
        api_keys: 有效的 API Key 集合
        exclude_paths: 免认证的路径集合
    """
    app.add_middleware(APIKeyAuthenticationMiddleware, api_keys=api_keys, exclude_paths=exclude_paths)
    logger.info(f"API 认证中间件已启用，已配置 {len(api_keys)} 个 API Key")
