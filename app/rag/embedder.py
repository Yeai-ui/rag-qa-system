"""
文本向量化模块（Embedding）。

三种模式：
- api  : 调用 OpenAI 兼容的 /embeddings 接口（推荐，速度快、效果佳）
- local: 使用本地 sentence-transformers 模型（CPU 可跑，需 pip install sentence-transformers）
- hash : 确定性哈希伪向量（零依赖，用于离线演示与流程验证，语义效果有限）

对外统一接口：Embedder.embed(texts: list[str]) -> list[list[float]]
"""
from __future__ import annotations

import hashlib
import math

import httpx

from app.core.config import settings


class BaseEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class APIEmbedder(BaseEmbedder):
    """OpenAI 兼容 embedding 接口。"""

    def __init__(self) -> None:
        self.base_url = settings.EMBEDDING_BASE_URL.rstrip("/")
        self.api_key = settings.EMBEDDING_API_KEY or settings.LLM_API_KEY
        self.model = settings.EMBEDDING_MODEL
        self.dim = settings.EMBEDDING_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.api_key:
            raise RuntimeError(
                "EMBEDDING_PROVIDER=api 但未配置 API Key，请在 .env 中设置 EMBEDDING_API_KEY，"
                "或改用 EMBEDDING_PROVIDER=hash 进行离线演示"
            )
        # 批量请求，每次最多 32 条
        results: list[list[float]] = []
        for i in range(0, len(texts), 32):
            batch = texts[i : i + 32]
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    f"{self.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model, "input": batch},
                )
            if resp.status_code != 200:
                raise RuntimeError(f"Embedding 接口错误 {resp.status_code}: {resp.text[:200]}")
            data = resp.json()["data"]
            results.extend([item["embedding"] for item in sorted(data, key=lambda x: x["index"])])
        return results


class HashEmbedder(BaseEmbedder):
    """确定性哈希伪向量：用于离线演示（无任何外部依赖）。"""

    DIM = 256

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_vec(t) for t in texts]

    def _hash_vec(self, text: str) -> list[float]:
        vec = [0.0] * self.DIM
        # 基于字符 n-gram 的哈希特征（带符号计数），保证相似文本向量相近
        grams: set[str] = set()
        for n in (1, 2, 3):
            grams.update(text[i : i + n] for i in range(len(text) - n + 1))
        for g in grams:
            h = hashlib.md5(g.encode("utf-8")).digest()
            idx = int.from_bytes(h[:4], "big") % self.DIM
            sign = 1.0 if h[4] % 2 == 0 else -1.0
            vec[idx] += sign
        # L2 归一化
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class LocalEmbedder(BaseEmbedder):
    """本地 sentence-transformers（可选依赖）。"""

    def __init__(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "EMBEDDING_PROVIDER=local 需要安装 sentence-transformers: pip install sentence-transformers"
            ) from e
        self._model = SentenceTransformer(settings.LOCAL_EMBEDDING_MODEL)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [vec.tolist() for vec in vectors]


def create_embedder() -> BaseEmbedder:
    provider = settings.EMBEDDING_PROVIDER.lower()
    if provider == "api":
        return APIEmbedder()
    if provider == "local":
        return LocalEmbedder()
    return HashEmbedder()
