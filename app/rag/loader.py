"""
文档解析模块：将 PDF / DOCX / MD / TXT 解析为结构化文本块列表。

返回格式：[{ "text": str, "meta": {"page": int|None, "heading": str|None} }, ...]
"""
from __future__ import annotations

from pathlib import Path

from app.core.config import settings


class DocumentParseError(Exception):
    """文档解析失败。"""


def parse_document(file_path: str | Path) -> list[dict]:
    """
    根据扩展名分发解析。
    返回段落级文本块（保留段落边界，供后续切分）。
    """
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _parse_pdf(path)
    if ext == ".docx":
        return _parse_docx(path)
    if ext in (".md", ".txt"):
        return _parse_text(path)
    raise DocumentParseError(f"不支持的文件类型: {ext}")


def _parse_pdf(path: Path) -> list[dict]:
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover
        raise DocumentParseError("缺少 pypdf 依赖，请执行 pip install pypdf") from e

    try:
        reader = PdfReader(str(path))
    except Exception as e:
        raise DocumentParseError(f"PDF 读取失败: {e}") from e

    blocks: list[dict] = []
    for page_no, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = _clean(text)
        if text:
            blocks.append({"text": text, "meta": {"page": page_no, "heading": None}})
    if not blocks:
        raise DocumentParseError("PDF 未提取到文本（可能是扫描件，请使用 OCR 版本）")
    return blocks


def _parse_docx(path: Path) -> list[dict]:
    try:
        import docx  # python-docx
    except ImportError as e:  # pragma: no cover
        raise DocumentParseError("缺少 python-docx 依赖，请执行 pip install python-docx") from e

    try:
        document = docx.Document(str(path))
    except Exception as e:
        raise DocumentParseError(f"DOCX 读取失败: {e}") from e

    blocks: list[dict] = []
    current_heading: str | None = None
    for para in document.paragraphs:
        text = _clean(para.text)
        if not text:
            continue
        style_name = (para.style.name or "").lower() if para.style else ""
        if "heading" in style_name or style_name.startswith("标题"):
            current_heading = text[:50]
            blocks.append({"text": text, "meta": {"page": None, "heading": current_heading}})
        else:
            blocks.append({"text": text, "meta": {"page": None, "heading": current_heading}})
    if not blocks:
        # 尝试表格内容
        for table in document.tables:
            for row in table.rows:
                cells = [_clean(c.text) for c in row.cells]
                line = " | ".join([c for c in cells if c])
                if line:
                    blocks.append({"text": line, "meta": {"page": None, "heading": None}})
    if not blocks:
        raise DocumentParseError("DOCX 未解析到有效文本")
    return blocks


def _parse_text(path: Path) -> list[dict]:
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = path.read_text(encoding="gbk", errors="ignore")
    blocks: list[dict] = []
    current_heading: str | None = None
    for line in raw.splitlines():
        line = _clean(line)
        if not line:
            continue
        # Markdown 标题识别
        if line.startswith("#"):
            current_heading = line.lstrip("#").strip()[:50]
        blocks.append({"text": line, "meta": {"page": None, "heading": current_heading}})
    if not blocks:
        raise DocumentParseError("文本文件为空")
    return blocks


def _clean(text: str) -> str:
    """清理空白与不可见字符。"""
    text = text.replace("\u3000", " ").replace("\ufeff", "")
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join([ln for ln in lines if ln]).strip()
