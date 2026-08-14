"""
LLM 生成模块（OpenAI 兼容 Chat Completions）。

- api 模式：调用真实大模型，支持 SSE 流式输出；
- echo 模式：离线演示，返回结构化模拟答案，便于无 Key 环境验证全流程。
"""
from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from app.core.config import settings


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self) -> None:
        self.provider = settings.LLM_PROVIDER.lower()
        self.base_url = settings.LLM_BASE_URL.rstrip("/")
        self.api_key = settings.LLM_API_KEY
        self.model = settings.LLM_MODEL

    @property
    def is_echo(self) -> bool:
        return self.provider == "echo"

    # ---------- 非流式 ----------
    def chat(self, messages: list[dict]) -> str:
        if self.is_echo:
            return self._echo_answer(messages)
        if not self.api_key:
            raise LLMError(
                "LLM_PROVIDER=api 但未配置 LLM_API_KEY。请在 .env 中配置，"
                "或设置 LLM_PROVIDER=echo 进行离线演示。"
            )
        with httpx.Client(timeout=settings.LLM_TIMEOUT) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": settings.LLM_TEMPERATURE,
                    "max_tokens": settings.LLM_MAX_TOKENS,
                    "stream": False,
                },
            )
        if resp.status_code != 200:
            raise LLMError(f"LLM 接口错误 {resp.status_code}: {resp.text[:300]}")
        return resp.json()["choices"][0]["message"]["content"]

    # ---------- 流式 ----------
    async def chat_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        if self.is_echo:
            # 模拟逐字流式输出
            for piece in self._chunk_text(self._echo_answer(messages), 4):
                yield piece
            return
        if not self.api_key:
            raise LLMError("未配置 LLM_API_KEY，无法调用大模型")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": settings.LLM_TEMPERATURE,
            "max_tokens": settings.LLM_MAX_TOKENS,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise LLMError(f"LLM 接口错误 {resp.status_code}: {body[:300]}")
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                        delta = obj["choices"][0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content
                    except Exception:
                        continue

    # ---------- 工具 ----------
    def _echo_answer(self, messages: list[dict]) -> str:
        """离线演示：从 user 消息中解析参考资料并构造模拟答案。"""
        user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        query = ""
        refs: list[str] = []
        in_refs = False
        for line in user_msg.splitlines():
            if line.startswith("【当前问题】"):
                query = line.replace("【当前问题】", "").strip()
            elif line.startswith("【参考资料】"):
                in_refs = True
            elif line.startswith("【对话历史】") or line.startswith("【当前问题】"):
                in_refs = False
            elif in_refs and line.strip():
                refs.append(line.strip())
        parts = [
            "（离线演示模式：LLM_PROVIDER=echo，以下为模拟回答，配置真实 API Key 后即为大模型生成）",
            "",
            f"关于「{query or '你的问题'}」，根据知识库资料分析如下：",
        ]
        for i, ref in enumerate(refs[:3], start=1):
            snippet = ref[:80] + ("…" if len(ref) > 80 else "")
            parts.append(f"{i}. 相关资料指出：{snippet} [1]")
        parts.append("")
        parts.append("配置 .env 中的 LLM_API_KEY 后，此处将输出大模型的真实回答。")
        return "\n".join(parts)

    @staticmethod
    def _chunk_text(text: str, size: int) -> list[str]:
        return [text[i : i + size] for i in range(0, len(text), size)]


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
