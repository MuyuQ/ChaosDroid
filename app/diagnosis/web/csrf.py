"""CSRF 保护配置模块。

提供 CSRF (Cross-Site Request Forgery) 保护功能，防止跨站请求伪造攻击。
"""

import os
from typing import Optional

from fastapi_csrf_protect import CsrfProtect


@CsrfProtect.load_config
def get_csrf_config() -> list:
    """获取 CSRF 配置参数。

    从环境变量读取 CSRF 密钥，如果未设置则使用默认值（仅用于开发环境）。
    生产环境必须设置 CSRF_SECRET 环境变量。

    Returns:
        list: 包含键值对元组的配置列表
    """
    # 生产环境必须设置此环境变量
    secret_key = os.getenv("CSRF_SECRET", "tracelens-dev-csrf-secret-change-in-production")

    # CSRF cookie 名称
    cookie_name = "csrf_token"

    # CSRF token 在 cookie 中的键名
    cookie_key = "csrf"

    # CSRF token 在请求头中的键名
    token_key = "X-CSRF-Token"

    return [
        ("secret_key", secret_key),
        ("cookie_name", cookie_name),
        ("cookie_key", cookie_key),
        ("token_key", token_key),
    ]


# CsrfProtect 类本身作为依赖
csrf_protect = CsrfProtect