"""
文本切分模块：递归字符切分（RecursiveCharacterTextSplitter 的中文优化版）。

设计要点：
1. 优先按段落(\n\n)切分，保持语义完整性；
2. 再按句子(。！？；\n)切分；
3. 最后按固定字符长度硬切，保证 chunk 不超过 CHUNK_SIZE；
4. 相邻 chunk 保留 OVERLAP 重叠，避免上下文断裂。
"""
from __future__ import annotations

from app.core.config import settings

# 切分优先级：段落 -> 句子 -> 字符
_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]


def split_text(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
    """将整段文本切分为带重叠的 chunk 列表。"""
    chunk_size = chunk_size or settings.CHUNK_SIZE
    overlap = overlap or settings.CHUNK_OVERLAP
    overlap = min(overlap, chunk_size // 2)
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        # 找切分点：在 chunk_size 范围内从后往前找优先级最高的分隔符
        cut = _find_cut_point(remaining, chunk_size)
        chunk = remaining[:cut].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:]
        # 保留 overlap 字符用于下一块开头
        if len(remaining) > overlap:
            remaining = remaining[overlap:]
        else:
            remaining = ""
    return [c for c in chunks if c]


def _find_cut_point(text: str, chunk_size: int) -> int:
    """在尽量接近 chunk_size 的位置，选择语义优先级最高的切分点。"""
    if len(text) <= chunk_size:
        return len(text)
    window = text[:chunk_size]
    for sep in _SEPARATORS:
        if not sep:
            return chunk_size
        pos = window.rfind(sep)
        if pos > chunk_size // 2:  # 避免切分点过前导致小块过多
            return pos + len(sep)
    return chunk_size


def split_blocks(blocks: list[dict], chunk_size: int | None = None, overlap: int | None = None) -> list[dict]:
    """
    将段落块列表切分为 chunk。
    返回：[{"content": str, "meta": {...}}]
    """
    chunks: list[dict] = []
    seq = 0
    for block in blocks:
        for piece in split_text(block["text"], chunk_size, overlap):
            meta = dict(block["meta"])
            if "heading" in meta and not meta.get("heading"):
                meta["heading"] = None
            chunks.append({"content": piece, "meta": meta, "seq": seq})
            seq += 1
    return chunks
