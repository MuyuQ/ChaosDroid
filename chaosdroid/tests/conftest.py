"""Pytest配置文件。

提供共享的fixtures和配置。
"""
import asyncio
import pytest
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环。"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def setup_test_environment():
    """设置测试环境。"""
    # 设置测试环境变量
    os.environ["CHAOSDROID_DATABASE_PATH"] = ":memory:"
    os.environ["CHAOSDROID_LOG_LEVEL"] = "ERROR"

    yield

    # 清理
    if "CHAOSDROID_DATABASE_PATH" in os.environ:
        del os.environ["CHAOSDROID_DATABASE_PATH"]
    if "CHAOSDROID_LOG_LEVEL" in os.environ:
        del os.environ["CHAOSDROID_LOG_LEVEL"]