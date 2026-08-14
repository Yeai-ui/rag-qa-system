"""
对话接口：会话 CRUD + 流式/非流式问答。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db import get_db
from app.models import Conversation, KnowledgeBase, Message, User
from app.rag.pipeline import answer_non_stream, answer_stream
from app.schemas import (
    AskRequest,
    AskResponse,
    ConversationCreateRequest,
    ConversationResponse,
    MessageResponse,
)

router = APIRouter(prefix="/api/chat", tags=["对话"])


def _get_conv(db: Session, user: User, conv_id: int) -> Conversation:
    conv = db.get(Conversation, conv_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conv


def _check_kb(db: Session, user: User, kb_id: int) -> None:
    if kb_id <= 0:
        return
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None or kb.user_id != user.id:
        raise HTTPException(status_code=404, detail="知识库不存在")


# ---------- 会话 ----------
@router.get("/conversations", response_model=list[ConversationResponse])
def list_conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .limit(100)
        .all()
    )


@router.post("/conversations", response_model=ConversationResponse)
def create_conversation(
    req: ConversationCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_kb(db, user, req.kb_id)
    conv = Conversation(user_id=user.id, kb_id=req.kb_id, title=req.title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.delete("/conversations/{conv_id}")
def delete_conversation(
    conv_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    conv = _get_conv(db, user, conv_id)
    db.delete(conv)
    db.commit()
    return {"ok": True}


@router.get("/conversations/{conv_id}/messages", response_model=list[MessageResponse])
def list_messages(
    conv_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    conv = _get_conv(db, user, conv_id)
    return db.query(Message).filter(Message.conversation_id == conv.id).all()


# ---------- 问答 ----------
@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """非流式问答。"""
    _check_kb(db, user, req.kb_id)
    conv = Conversation(user_id=user.id, kb_id=req.kb_id, title="新对话")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    result = await answer_non_stream(db, conv, req.query, req.kb_id)
    return AskResponse(
        answer=result["answer"],
        sources=result["sources"],
        conversation_id=result.get("conversation_id", conv.id),
        message_id=result.get("message_id", 0),
    )


@router.post("/ask-stream")
async def ask_stream(req: AskRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """流式问答（SSE）。"""
    _check_kb(db, user, req.kb_id)
    conv = Conversation(user_id=user.id, kb_id=req.kb_id, title="新对话")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    async def event_generator():
        try:
            async for evt in answer_stream(db, conv, req.query, req.kb_id):
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            db.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
