"""SQLAlchemy 数据库基础配置。"""

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.diagnosis.config import settings


class Base(DeclarativeBase):
    """SQLAlchemy 基类。"""

    pass


# 数据库引擎和会话
_engine = None
_session_factory = None


def get_engine():
    """获取数据库引擎。"""
    global _engine
    if _engine is None:
        # 确保数据目录存在
        db_path = Path(settings.database_url.replace("sqlite:///", ""))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(settings.database_url, echo=False)
    return _engine


def get_session_factory():
    """获取会话工厂。"""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine())
    return _session_factory


def get_session() -> Session:
    """获取数据库会话。"""
    return get_session_factory()()


def init_db():
    """初始化数据库表。"""
    Base.metadata.create_all(get_engine())


def reset_engine():
    """重置数据库引擎缓存（用于测试）。"""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def reset_db():
    """重置数据库（仅用于测试）。"""
    reset_engine()
    engine = get_engine()
    # 使用 checkfirst=False 强制删除所有表
    Base.metadata.drop_all(engine, checkfirst=True)
    Base.metadata.create_all(engine)