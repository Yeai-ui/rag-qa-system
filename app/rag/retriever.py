"""
向量存储与检索模块（基于 ChromaDB 持久化）。

功能：
1. 每个知识库一个 collection，命名 kb_{kb_id}；
2. 支持向量语义检索（余弦相似度）；
3. 可选 BM25 关键词检索（jieba 分词），通过 RRF 算法与向量结果融合；
4. 返回带来源元数据的检索结果，供 LLM 生成引用。
"""
from __future__ import annotations

import math
from collections import Counter

import chromadb

from app.core.config import settings


class Retriever:
    def __init__(self) -> None:
        settings.VECTOR_DIR.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(settings.VECTOR_DIR))
        self._embedder = None  # 延迟注入，避免循环依赖

    def set_embedder(self, embedder) -> None:
        self._embedder = embedder

    # ---------- 集合管理 ----------
    def _collection(self, kb_id: int, create: bool = True):
        name = f"kb_{kb_id}"
        try:
            return self._client.get_collection(name)
        except Exception:
            if create:
                return self._client.create_collection(
                    name=name, metadata={"hnsw:space": "cosine"}
                )
            raise

    def delete_collection(self, kb_id: int) -> None:
        try:
            self._client.delete_collection(f"kb_{kb_id}")
        except Exception:
            pass

    def collection_count(self, kb_id: int) -> int:
        try:
            return self._collection(kb_id, create=False).count()
        except Exception:
            return 0

    # ---------- 写入 ----------
    def add_chunks(self, kb_id: int, chunks: list[dict], embeddings: list[list[float]]) -> list[str]:
        """批量写入 chunk，返回生成的 vector_id 列表。"""
        col = self._collection(kb_id)
        ids = [f"kb{kb_id}_c{chunks[i]['seq']}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "kb_id": kb_id,
                "doc_id": chunks[i]["doc_id"],
                "seq": chunks[i]["seq"],
                "heading": (chunks[i]["meta"] or {}).get("heading") or "",
                "page": (chunks[i]["meta"] or {}).get("page") or 0,
            }
            for i in range(len(chunks))
        ]
        # 分批写入，避免单次过大
        for i in range(0, len(chunks), 200):
            col.add(
                ids=ids[i : i + 200],
                embeddings=embeddings[i : i + 200],
                documents=[c["content"] for c in chunks[i : i + 200]],
                metadatas=metadatas[i : i + 200],
            )
        return ids

    def delete_chunks_by_doc(self, kb_id: int, vector_ids: list[str]) -> None:
        if not vector_ids:
            return
        try:
            col = self._collection(kb_id, create=False)
            for i in range(0, len(vector_ids), 100):
                col.delete(ids=vector_ids[i : i + 100])
        except Exception:
            pass

    # ---------- 检索 ----------
    def search(self, query: str, kb_id: int, top_k: int | None = None) -> list[dict]:
        """
        混合检索：向量相似度 + BM25，RRF 融合。
        返回：[{"content","meta","score","doc_id","seq"}, ...]
        """
        if self._embedder is None:
            return []
        top_k = top_k or settings.TOP_K
        try:
            col = self._collection(kb_id, create=False)
        except Exception:
            return []

        query_vec = self._embedder.embed_one(query)

        # 1) 向量检索：多取 2 倍候选用于融合
        n_vec = max(top_k * 2, top_k + 3)
        vec_res = col.query(query_embeddings=[query_vec], n_results=n_vec)
        vec_hits: list[dict] = []
        if vec_res and vec_res["ids"] and vec_res["ids"][0]:
            for vid, doc, meta, dist in zip(
                vec_res["ids"][0],
                vec_res["documents"][0],
                vec_res["metadatas"][0],
                vec_res["distances"][0],
            ):
                vec_hits.append(
                    {
                        "vector_id": vid,
                        "content": doc,
                        "meta": meta or {},
                        "score": 1.0 - float(dist),  # 余弦距离转相似度
                    }
                )

        # 2) BM25 检索
        bm25_hits: list[dict] = []
        if settings.ENABLE_BM25:
            bm25_hits = self._bm25_search(col, query, kb_id, top_k=max(top_k * 2, top_k + 3))

        # 3) RRF 融合
        raw_results = self._rrf_fusion(vec_hits, bm25_hits, top_k * 3)
        return self._filter_noise(raw_results, top_k)

    def _filter_noise(self, results: list[dict], top_k: int) -> list[dict]:
        """过滤目录页、声明页、致谢页、页眉页脚等噪音 chunk，优先保留正文内容。"""
        filtered = []
        noise_prefixes = (
            "学位论文原创性声明", "郑重声明", "版权使用授权书",
            "致谢", "目录", "目次",
        )
        for r in results:
            content = r.get("content", "")
            # 过滤目录页（大量连续点号/省略号作为页码引导符）
            if content.count("....") >= 3 or content.count("……") >= 3:
                continue
            # 过滤过短文本（少于 30 字，大概率是标题或页眉页脚）
            if len(content.strip()) < 30:
                continue
            # 过滤声明页、授权书页、致谢页、目录页等噪音（看前 120 字）
            head = content[:120]
            if any(p in head for p in noise_prefixes):
                continue
            filtered.append(r)
            if len(filtered) >= top_k:
                break
        # 若过滤后不足 top_k，从原始结果中补充（避免漏掉真正需要的内容）
        if len(filtered) < top_k:
            existing_vids = {h.get("vector_id") for h in filtered}
            for r in results:
                if r.get("vector_id") not in existing_vids:
                    filtered.append(r)
                    if len(filtered) >= top_k:
                        break
        return filtered

    # ---------- BM25 ----------
    def _bm25_search(self, col, query: str, kb_id: int, top_k: int) -> list[dict]:
        try:
            all_data = col.get(include=["documents", "metadatas"])
        except Exception:
            return []
        if not all_data or not all_data["ids"]:
            return []

        docs = all_data["documents"]
        metas = all_data["metadatas"]
        ids = all_data["ids"]
        corpus = [self._tokenize(d) for d in docs]
        q_tokens = self._tokenize(query)
        if not q_tokens:
            return []

        # 文档频率
        df: Counter = Counter()
        for tokens in corpus:
            for t in set(tokens):
                df[t] += 1
        n_docs = len(corpus)
        avg_len = sum(len(t) for t in corpus) / max(n_docs, 1)
        k1, b = 1.5, 0.75

        scores: list[tuple[float, int]] = []
        for idx, tokens in enumerate(corpus):
            if not tokens:
                continue
            tf = Counter(tokens)
            score = 0.0
            for t in q_tokens:
                f = tf.get(t, 0)
                if f == 0:
                    continue
                idf = math.log(1 + (n_docs - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * len(tokens) / avg_len))
            if score > 0:
                scores.append((score, idx))
        scores.sort(key=lambda x: x[0], reverse=True)

        hits = []
        for score, idx in scores[:top_k]:
            hits.append(
                {
                    "vector_id": ids[idx],
                    "content": docs[idx],
                    "meta": metas[idx] or {},
                    "score": float(score),
                }
            )
        return hits

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        import jieba

        words = jieba.lcut(text.lower())
        return [w for w in words if w.strip() and w.strip() not in ("的", "了", "是", "在", "和", "与")]

    # ---------- RRF 融合 ----------
    @staticmethod
    def _rrf_fusion(vec_hits: list[dict], bm25_hits: list[dict], top_k: int) -> list[dict]:
        K = 60.0
        rank: dict[str, float] = {}
        meta_map: dict[str, dict] = {}
        score_map: dict[str, float] = {}
        for rank_i, hits in enumerate((vec_hits, bm25_hits)):
            for pos, h in enumerate(hits):
                vid = h["vector_id"]
                rank[vid] = rank.get(vid, 0.0) + 1.0 / (K + pos + 1)
                meta_map.setdefault(vid, h)
                score_map.setdefault(vid, h.get("score", 0.0))
        ordered = sorted(rank.items(), key=lambda x: x[1], reverse=True)
        results = []
        for vid, r in ordered[:top_k]:
            h = meta_map[vid]
            results.append(
                {
                    "vector_id": vid,
                    "content": h["content"],
                    "meta": h["meta"],
                    "score": round(r, 4),
                    "doc_id": h["meta"].get("doc_id"),
                    "seq": h["meta"].get("seq", 0),
                }
            )
        return results


_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever
