"""
RAG 主流程编排模块。

1. process_document: 文档解析 -> 切分 -> 向量化 -> 向量库入库 -> 更新元数据库
2. remove_document:  删除文档对应的向量与元数据
3. answer:           检索 -> 组装 prompt -> LLM 生成（流式/非流式）
"""
from __future__ import annotations

import traceback
from typing import AsyncIterator

from sqlalchemy.orm import Session

from app.models import Chunk, Conversation, Document, KnowledgeBase, Message
from app.rag import loader, splitter
from app.rag.embedder import create_embedder
from app.rag.generator import get_llm
from app.rag.prompts import build_qa_messages
from app.rag.retriever import get_retriever

# 全局共享实例（向量库与 embedding 复用，避免重复初始化）
_embedder = create_embedder()
get_retriever().set_embedder(_embedder)


# ---------- 文档处理 ----------
def process_document(db: Session, doc: Document) -> None:
    """将 Document 从 pending 处理为 ready / failed。"""
    doc.status = "processing"
    db.commit()

    try:
        blocks = loader.parse_document(doc.file_path)
        chunks = splitter.split_blocks(blocks)
        if not chunks:
            raise loader.DocumentParseError("文档切分后无有效文本块")

        # 向量化
        texts = [c["content"] for c in chunks]
        embeddings = _embedder.embed(texts)

        # 入库前先清理旧数据（幂等）
        _purge_doc_from_vector(db, doc)

        # 向量入库
        for i, c in enumerate(chunks):
            c["doc_id"] = doc.id
            c["seq"] = i
        vector_ids = get_retriever().add_chunks(doc.kb_id, chunks, embeddings)

        # 元数据入库
        for i, c in enumerate(chunks):
            db.add(
                Chunk(
                    kb_id=doc.kb_id,
                    doc_id=doc.id,
                    seq=i,
                    content=c["content"],
                    meta=c["meta"],
                    vector_id=vector_ids[i],
                )
            )
        db.flush()

        doc.status = "ready"
        doc.chunk_count = len(chunks)
        doc.error_msg = ""
        _refresh_kb_stats(db, doc.kb_id)
        db.commit()
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        doc.status = "failed"
        doc.error_msg = str(e)[:500]
        db.commit()


def _purge_doc_from_vector(db: Session, doc: Document) -> None:
    vector_ids = db.query(Chunk.vector_id).filter(Chunk.doc_id == doc.id).all()
    ids = [v[0] for v in vector_ids if v[0]]
    if ids:
        get_retriever().delete_chunks_by_doc(doc.kb_id, ids)
    db.query(Chunk).filter(Chunk.doc_id == doc.id).delete()
    db.commit()


def remove_document(db: Session, doc: Document) -> None:
    """删除文档（向量 + 元数据）。"""
    _purge_doc_from_vector(db, doc)
    db.delete(doc)
    _refresh_kb_stats(db, doc.kb_id)
    db.commit()


def _refresh_kb_stats(db: Session, kb_id: int) -> None:
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None:
        return
    kb.doc_count = db.query(Document).filter(Document.kb_id == kb_id).count()
    kb.chunk_count = db.query(Chunk).filter(Chunk.kb_id == kb_id).count()
    db.commit()


# ---------- 问答 ----------
def retrieve_contexts(query: str, kb_id: int, limit: int | None = None) -> list[dict]:
    """检索相关上下文。"""
    if kb_id <= 0:
        return []
    hits = get_retriever().search(query, kb_id)
    return hits[: (limit or 5)]


async def answer_stream(
    db: Session,
    conversation: Conversation,
    query: str,
    kb_id: int,
) -> AsyncIterator[dict]:
    """
    流式问答：先检索，再流式生成。
    产出事件：
      {"type": "sources", "data": [...]}
      {"type": "delta", "data": "文本片段"}
      {"type": "done", "data": {"conversation_id":.., "message_id":..}}
      {"type": "error", "data": "错误信息"}
    """
    try:
        # 1. 检索
        contexts = retrieve_contexts(query, kb_id)

        # 2. 组装历史
        history_rows = (
            db.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .order_by(Message.id.desc())
            .limit(6)
            .all()
        )
        history = [{"role": m.role, "content": m.content} for m in reversed(history_rows)]

        # 3. 组装 prompt
        messages = build_qa_messages(query, contexts, history)

        # 4. 保存用户消息
        user_msg = Message(conversation_id=conversation.id, role="user", content=query, sources=[])
        db.add(user_msg)
        db.flush()
        user_msg_id = user_msg.id

        # 5. 来源信息
        sources = [
            {
                "content": c["content"][:400],
                "doc_id": c.get("doc_id"),
                "seq": c.get("seq", 0),
                "score": c.get("score", 0),
                "heading": (c.get("meta") or {}).get("heading") or "",
                "page": (c.get("meta") or {}).get("page") or 0,
            }
            for c in contexts
        ]
        yield {"type": "sources", "data": sources}

        # 6. 生成（流式）
        answer_parts: list[str] = []
        llm = get_llm()
        async for piece in llm.chat_stream(messages):
            answer_parts.append(piece)
            yield {"type": "delta", "data": piece}

        answer = "".join(answer_parts).strip() or "（模型未返回内容，请重试）"

        # 7. 保存助手消息
        assistant_msg = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            sources=sources,
            tokens=0,
        )
        db.add(assistant_msg)
        db.flush()
        conversation.title = conversation.title if conversation.title != "新对话" else query[:30]
        db.commit()

        yield {
            "type": "done",
            "data": {
                "conversation_id": conversation.id,
                "message_id": assistant_msg.id,
                "user_message_id": user_msg_id,
            },
        }
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        yield {"type": "error", "data": str(e)}


async def answer_non_stream(
    db: Session,
    conversation: Conversation,
    query: str,
    kb_id: int,
) -> dict:
    """非流式问答（内部聚合流式事件）。"""
    full_answer = ""
    sources: list = []
    done: dict = {}
    async for evt in answer_stream(db, conversation, query, kb_id):
        if evt["type"] == "sources":
            sources = evt["data"]
        elif evt["type"] == "delta":
            full_answer += evt["data"]
        elif evt["type"] == "done":
            done = evt["data"]
        elif evt["type"] == "error":
            raise RuntimeError(evt["data"])
    return {"answer": full_answer, "sources": sources, **done}
