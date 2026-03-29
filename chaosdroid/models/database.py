"""
数据库引擎和会话管理模块。

提供异步数据库连接和会话管理功能。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .base import Base

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


# 默认数据库路径
DEFAULT_DATABASE_PATH = "chaosdroid.db"

# 全局引擎实例
_engine: "AsyncEngine | None" = None

# 全局会话工厂
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_database_url(database_path: str = DEFAULT_DATABASE_PATH) -> str:
    """
    获取数据库连接URL。

    Args:
        database_path: 数据库文件路径

    Returns:
        异步SQLite数据库连接URL
    """
    return f"sqlite+aiosqlite:///{database_path}"


def init_engine(database_path: str = DEFAULT_DATABASE_PATH) -> "AsyncEngine":
    """
    初始化数据库引擎。

    Args:
        database_path: 数据库文件路径

    Returns:
        异步数据库引擎实例
    """
    global _engine, _session_factory

    if _engine is not None:
        return _engine

    database_url = get_database_url(database_path)

    _engine = create_async_engine(
        database_url,
        echo=False,  # 设置为True可以看到SQL语句
        future=True,
        pool_pre_ping=True,  # 连接池预检查
    )

    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    return _engine


def get_engine() -> "AsyncEngine":
    """
    获取数据库引擎实例。

    Returns:
        异步数据库引擎实例

    Raises:
        RuntimeError: 如果引擎未初始化
    """
    if _engine is None:
        raise RuntimeError("数据库引擎未初始化，请先调用 init_engine()")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    获取会话工厂实例。

    Returns:
        异步会话工厂实例

    Raises:
        RuntimeError: 如果会话工厂未初始化
    """
    if _session_factory is None:
        raise RuntimeError("数据库引擎未初始化，请先调用 init_engine()")
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库会话（用于依赖注入）。

    Yields:
        异步数据库会话实例

    Example:
        ```python
        @app.get("/items")
        async def get_items(session: AsyncSession = Depends(get_session)):
            ...
        ```
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """
    获取数据库会话上下文管理器。

    Yields:
        异步数据库会话实例

    Example:
        ```python
        async with get_session_context() as session:
            result = await session.execute(select(ScenarioTemplate))
            templates = result.scalars().all()
        ```
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables() -> None:
    """
    创建所有数据库表。

    此方法会根据模型定义创建所有表结构。
    如果表已存在则不会重复创建。
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables() -> None:
    """
    删除所有数据库表。

    此方法会删除所有表结构，谨慎使用。
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def close_engine() -> None:
    """
    关闭数据库引擎。

    释放所有连接池资源。
    """
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None