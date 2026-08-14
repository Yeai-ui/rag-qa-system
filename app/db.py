"""
数据库初始化：SQLite + SQLAlchemy 2.0，建表并注入默认数据。
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings, ensure_dirs


class Base(DeclarativeBase):
    """ORM 声明基类。"""


def _init_engine() -> tuple:
    ensure_dirs()
    db_path: Path = settings.DB_PATH
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, SessionLocal


engine, SessionLocal = _init_engine()


def get_db():
    """FastAPI 依赖：请求级数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """创建所有表。"""
    # 导入模型以注册到 Base.metadata
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
