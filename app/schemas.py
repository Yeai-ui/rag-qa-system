"""
Pydantic 请求/响应模型（API 契约）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------- 认证 ----------
class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class UserResponse(BaseModel):
    id: int
    username: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- 知识库 ----------
class KBCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""


class KBResponse(BaseModel):
    id: int
    name: str
    description: str
    doc_count: int
    chunk_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentResponse(BaseModel):
    id: int
    kb_id: int
    filename: str
    file_type: str
    file_size: int
    status: str
    chunk_count: int
    error_msg: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- 对话 ----------
class ConversationCreateRequest(BaseModel):
    kb_id: int = 0
    title: str = "新对话"


class ConversationResponse(BaseModel):
    id: int
    kb_id: int
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    sources: list
    tokens: int
    created_at: datetime

    class Config:
        from_attributes = True


class AskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    kb_id: int = 0  # 0 = 不限定
    stream: bool = True


class AskResponse(BaseModel):
    answer: str
    sources: list
    conversation_id: int
    message_id: int


# ---------- 统计 ----------
class StatsResponse(BaseModel):
    user_id: int
    kb_count: int
    doc_count: int
    chunk_count: int
    conversation_count: int
    message_count: int
    kb_stats: list[dict[str, Any]]
