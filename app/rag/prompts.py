"""
提示词工程模块：RAG 问答 prompt 模板与历史消息组装。
"""
from __future__ import annotations

SYSTEM_PROMPT = """你是一个严谨的智能知识问答助手，基于用户提供的知识库资料回答问题。

## 回答要求
1. 只能依据【参考资料】中的内容回答，不要编造参考资料中没有的信息；
2. 若参考资料不足，明确回答"根据现有资料无法回答"，并提示用户补充资料；
3. 回答时在相关句末标注引用编号，格式为 [1]、[2]（对应参考资料编号）；
4. 使用清晰的中文，分点或分段组织回答，便于阅读；
5. 若问题是闲聊或与资料无关，礼貌说明并引导用户提问知识库相关问题。
"""


def build_qa_messages(
    query: str,
    contexts: list[dict],
    history: list[dict] | None = None,
) -> list[dict]:
    """
    组装 messages：
    - system: 固定指令
    - user: 包含历史对话 + 参考资料 + 当前问题
    """
    history = history or []
    # 历史只取最近 6 条，控制上下文长度
    recent = history[-6:]

    ref_lines = []
    for i, ctx in enumerate(contexts, start=1):
        src = ctx.get("source_name") or ""
        page = ctx.get("meta", {}).get("page") or ""
        loc = f"（来源：{src}" + (f"，第{page}页）" if page else "）")
        ref_lines.append(f"[{i}] {ctx['content']}{loc}")
    ref_text = "\n\n".join(ref_lines) if ref_lines else "（无参考资料）"

    user_parts: list[str] = []
    if recent:
        history_lines = []
        for m in recent:
            role = "用户" if m.get("role") == "user" else "助手"
            history_lines.append(f"{role}: {m['content'][:300]}")
        user_parts.append("【对话历史】\n" + "\n".join(history_lines))
    user_parts.append("【参考资料】\n" + ref_text)
    user_parts.append(f"【当前问题】\n{query}")
    user_parts.append("请严格依据参考资料回答，并标注引用编号。")

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]
