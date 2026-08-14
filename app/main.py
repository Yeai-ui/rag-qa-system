"""
应用入口：FastAPI 实例、路由注册、静态资源托管、启动初始化。
启动命令：uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, chat, kb, stats
from app.core.config import settings
from app.db import init_db

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description=settings.APP_NAME_EN,
)

# CORS（允许本地开发前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由注册
app.include_router(auth.router)
app.include_router(kb.router)
app.include_router(chat.router)
app.include_router(stats.router)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "llm_provider": settings.LLM_PROVIDER,
        "embedding_provider": settings.EMBEDDING_PROVIDER,
    }


# ---------- 前端静态资源 ----------
WEB_DIR: Path = settings.WEB_DIR
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index():
    index_path = WEB_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return JSONResponse({"message": "RAG QA System API", "docs": "/docs"})


@app.on_event("startup")
def startup() -> None:
    init_db()
