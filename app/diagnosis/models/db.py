"""SQLAlchemy 数据库配置 - 异步版本。"""

from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.diagnosis.config import settings


class Base(DeclarativeBase):
    """SQLAlchemy 基类。"""

    pass


# 数据库引擎和会话
_engine = None
_async_session_factory = None


def get_engine():
    """获取异步数据库引擎。"""
    global _engine
    if _engine is None:
        # 确保数据目录存在
        db_path = Path(settings.database_url.replace("sqlite+aiosqlite:///", ""))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_async_engine(settings.database_url, echo=False)
    return _engine


def get_async_session_factory():
    """获取异步会话工厂。"""
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


async def get_session() -> AsyncSession:
    """获取异步数据库会话。

    用作依赖注入的生成器。
    """
    async with get_async_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_session_context() -> AsyncSession:
    """获取异步数据库会话（用于上下文管理器）。

    返回会话对象，调用者负责 commit/rollback 和 close。
    """
    return await get_async_session_factory()().__aenter__()


async def init_db():
    """初始化数据库表。"""
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def reset_engine():
    """重置数据库引擎缓存（用于测试）。"""
    global _engine, _async_session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _async_session_factory = None


async def reset_db():
    """重置数据库（仅用于测试）。"""
    await reset_engine()
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
