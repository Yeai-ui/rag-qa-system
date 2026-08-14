"""
全局配置模块：从环境变量 / .env 文件加载所有运行参数。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（app/ 的上一级）
BASE_DIR = Path(__file__).resolve().parent.parent.parent
# 加载 .env（若存在）
load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str = "") -> str:
    """读取环境变量并去除首尾空白。"""
    return os.getenv(key, default).strip()


class Settings:
    """应用运行配置（单例通过 get_settings() 获取）。"""

    # ---------- 应用基本信息 ----------
    APP_NAME: str = "基于大语言模型的智能领域知识问答系统"
    APP_NAME_EN: str = "Smart Knowledge Q&A System based on LLM"
    VERSION: str = "1.0.0"

    # ---------- 目录 ----------
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    VECTOR_DIR: Path = DATA_DIR / "chroma"
    DB_PATH: Path = DATA_DIR / "app.db"
    WEB_DIR: Path = BASE_DIR / "app" / "web"

    # ---------- 安全 / JWT ----------
    SECRET_KEY: str = _env("SECRET_KEY", "rag-qa-insecure-secret-change-me")
    ALGORITHM: str = "HS256"
    TOKEN_EXPIRE_MINUTES: int = int(_env("TOKEN_EXPIRE_MINUTES", "10080"))

    # ---------- LLM ----------
    # provider: api | echo
    LLM_PROVIDER: str = _env("LLM_PROVIDER", "api")
    LLM_API_KEY: str = _env("LLM_API_KEY", "")
    LLM_BASE_URL: str = _env("LLM_BASE_URL", "https://api.deepseek.com/v1")
    LLM_MODEL: str = _env("LLM_MODEL", "deepseek-chat")
    LLM_TEMPERATURE: float = float(_env("LLM_TEMPERATURE", "0.3"))
    LLM_MAX_TOKENS: int = int(_env("LLM_MAX_TOKENS", "1024"))
    LLM_TIMEOUT: float = 120.0

    # ---------- Embedding ----------
    # provider: api | local | hash
    EMBEDDING_PROVIDER: str = _env("EMBEDDING_PROVIDER", "hash")
    EMBEDDING_API_KEY: str = _env("EMBEDDING_API_KEY", "")
    EMBEDDING_BASE_URL: str = _env("EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1")
    EMBEDDING_MODEL: str = _env("EMBEDDING_MODEL", "BAAI/bge-m3")
    LOCAL_EMBEDDING_MODEL: str = _env("LOCAL_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    EMBEDDING_DIM: int = 1024  # 实际维度由向量库自动确定，此值仅用于 hash 模式

    # ---------- 文档切分 ----------
    CHUNK_SIZE: int = int(_env("CHUNK_SIZE", "500"))
    CHUNK_OVERLAP: int = int(_env("CHUNK_OVERLAP", "80"))

    # ---------- 检索 ----------
    TOP_K: int = int(_env("TOP_K", "5"))
    ENABLE_BM25: bool = _env("ENABLE_BM25", "true").lower() in ("1", "true", "yes")
    # 混合检索融合参数（BM25 结果占 TOP_K 的比例）
    BM25_RATIO: float = 0.4

    # ---------- 允许上传的文件类型 ----------
    ALLOWED_EXTENSIONS: tuple = (".pdf", ".docx", ".md", ".txt")
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB


def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def ensure_dirs() -> None:
    """确保所有数据目录存在。"""
    for d in (settings.DATA_DIR, settings.UPLOAD_DIR, settings.VECTOR_DIR):
        d.mkdir(parents=True, exist_ok=True)
