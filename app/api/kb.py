"""
知识库管理接口：知识库 CRUD、文档上传/列表/删除/重新处理。
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models import Conversation, Document, KnowledgeBase, User
from app.rag.pipeline import process_document, remove_document
from app.rag.retriever import get_retriever
from app.schemas import (
    DocumentResponse,
    KBCreateRequest,
    KBResponse,
)
from app.core.security import get_current_user

router = APIRouter(prefix="/api/kb", tags=["知识库"])


def _get_kb(db: Session, user: User, kb_id: int) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None or kb.user_id != user.id:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return kb


# ---------- 知识库 ----------
@router.get("", response_model=list[KBResponse])
def list_kb(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(KnowledgeBase).filter(KnowledgeBase.user_id == user.id).all()


@router.post("", response_model=KBResponse)
def create_kb(
    req: KBCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kb = KnowledgeBase(user_id=user.id, name=req.name, description=req.description)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


@router.delete("/{kb_id}")
def delete_kb(kb_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kb = _get_kb(db, user, kb_id)
    # 删除向量集合
    get_retriever().delete_collection(kb_id)
    # 删除关联会话
    db.query(Conversation).filter(Conversation.kb_id == kb_id).delete()
    db.delete(kb)
    db.commit()
    return {"ok": True}


@router.put("/{kb_id}", response_model=KBResponse)
def update_kb(
    kb_id: int,
    req: KBCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kb = _get_kb(db, user, kb_id)
    kb.name = req.name
    kb.description = req.description
    db.commit()
    db.refresh(kb)
    return kb


# ---------- 文档 ----------
@router.get("/{kb_id}/docs", response_model=list[DocumentResponse])
def list_docs(kb_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_kb(db, user, kb_id)
    return (
        db.query(Document)
        .filter(Document.kb_id == kb_id)
        .order_by(Document.id.desc())
        .all()
    )


@router.post("/{kb_id}/docs", response_model=DocumentResponse)
async def upload_doc(
    kb_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    kb = _get_kb(db, user, kb_id)
    filename = file.filename or "unnamed"
    ext = Path(filename).suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 {ext}，支持: {', '.join(settings.ALLOWED_EXTENSIONS)}",
        )

    # 同名文档拦截
    exists = (
        db.query(Document).filter(Document.kb_id == kb_id, Document.filename == filename).first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="知识库中已存在同名文档")

    # 保存文件
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    save_name = f"{uuid.uuid4().hex}{ext}"
    save_path = settings.UPLOAD_DIR / save_name
    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="文件超过 50MB 限制")
    save_path.write_bytes(content)

    doc = Document(
        kb_id=kb_id,
        filename=filename,
        file_path=str(save_path),
        file_type=ext.lstrip("."),
        file_size=len(content),
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 同步处理（文档不大时足够；超大文档可改为后台任务）
    process_document(db, doc)
    db.refresh(doc)
    if doc.status == "failed":
        raise HTTPException(status_code=422, detail=f"文档解析失败: {doc.error_msg}")
    return doc


@router.delete("/{kb_id}/docs/{doc_id}")
def delete_doc(
    kb_id: int,
    doc_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_kb(db, user, kb_id)
    doc = db.get(Document, doc_id)
    if doc is None or doc.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    remove_document(db, doc)
    return {"ok": True}


@router.post("/{kb_id}/docs/{doc_id}/reprocess", response_model=DocumentResponse)
def reprocess_doc(
    kb_id: int,
    doc_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_kb(db, user, kb_id)
    doc = db.get(Document, doc_id)
    if doc is None or doc.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    process_document(db, doc)
    db.refresh(doc)
    return doc
