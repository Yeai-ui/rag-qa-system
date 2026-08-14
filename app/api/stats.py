"""统计接口：数据仪表盘所需聚合数据。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db import get_db
from app.models import Chunk, Conversation, Document, KnowledgeBase, Message, User
from app.schemas import StatsResponse

router = APIRouter(prefix="/api/stats", tags=["统计"])


@router.get("", response_model=StatsResponse)
def stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kb_list = db.query(KnowledgeBase).filter(KnowledgeBase.user_id == user.id).all()
    kb_ids = [kb.id for kb in kb_list]

    doc_count = 0
    chunk_count = 0
    kb_stats: list[dict] = []
    for kb in kb_list:
        docs = db.query(func.count(Document.id)).filter(Document.kb_id == kb.id).scalar() or 0
        chunks = db.query(func.count(Chunk.id)).filter(Chunk.kb_id == kb.id).scalar() or 0
        doc_count += docs
        chunk_count += chunks
        kb_stats.append({"kb_id": kb.id, "name": kb.name, "docs": docs, "chunks": chunks})

    conv_count = db.query(func.count(Conversation.id)).filter(Conversation.user_id == user.id).scalar() or 0
    msg_count = 0
    conv_ids = (
        db.query(Conversation.id).filter(Conversation.user_id == user.id).all()
    )
    if conv_ids:
        conv_id_list = [c[0] for c in conv_ids]
        msg_count = (
            db.query(func.count(Message.id)).filter(Message.conversation_id.in_(conv_id_list)).scalar() or 0
        )

    return StatsResponse(
        user_id=user.id,
        kb_count=len(kb_list),
        doc_count=doc_count,
        chunk_count=chunk_count,
        conversation_count=conv_count,
        message_count=msg_count,
        kb_stats=kb_stats,
    )
