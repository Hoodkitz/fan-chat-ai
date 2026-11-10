"""Hybrid retrieval over long-term memory facts: lexical (tsvector) + vector, fused with RRF.

No separate vector database: everything stays in PostgreSQL under RLS. Embeddings come from
an ``EmbeddingPort`` (deterministic hashing fake for tests/dev, pluggable for production).
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain.models import MemoryFact

RRF_K = 60
BRANCH_LIMIT = 30
TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöüß0-9]{2,}")


class EmbeddingPort(Protocol):
    dim: int

    def embed(self, text: str) -> list[float]: ...


class HashingEmbedding:
    """Deterministic bag-of-words hashing embedding (no external model). Good enough to test the
    plumbing and to give lexical-ish similarity; swap for a real model in production."""
    dim = 256

    def embed(self, s: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in TOKEN_RE.findall((s or "").lower()):
            h = int(hashlib.blake2b(tok.encode(), digest_size=4).hexdigest(), 16)
            v[h % self.dim] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]


_emb: EmbeddingPort = HashingEmbedding()


def get_embedding() -> EmbeddingPort:
    return _emb


def set_embedding(e: EmbeddingPort) -> None:
    global _emb
    _emb = e


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def rrf(*rankings: list, k: int = RRF_K) -> list[tuple[object, float]]:
    """Reciprocal Rank Fusion over ranked id lists. Returns (id, score) sorted desc."""
    scores: dict = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: -kv[1])


def lexical_search(db: Session, fan_id, query: str, limit: int = BRANCH_LIMIT) -> list:
    rows = db.execute(text(
        "SELECT id FROM memory_facts WHERE fan_id = :f AND tsv @@ plainto_tsquery('german', :q) "
        "ORDER BY ts_rank(tsv, plainto_tsquery('german', :q)) DESC, created_at DESC LIMIT :n"),
        {"f": str(fan_id), "q": query, "n": limit}).all()
    return [r[0] for r in rows]


def vector_search(db: Session, fan_id, query: str, limit: int = BRANCH_LIMIT) -> list:
    q = get_embedding().embed(query)
    facts = db.query(MemoryFact.id, MemoryFact.embedding).filter(MemoryFact.fan_id == fan_id).all()
    scored = [(fid, cosine(q, emb or [])) for fid, emb in facts]
    scored = [s for s in scored if s[1] > 0]
    scored.sort(key=lambda s: -s[1])
    return [fid for fid, _ in scored[:limit]]


def search_facts(db: Session, fan_id, query: str, limit: int = 5) -> list[MemoryFact]:
    if not (query or "").strip():
        return []
    fused = rrf(lexical_search(db, fan_id, query), vector_search(db, fan_id, query))
    ids = [fid for fid, _ in fused[:limit]]
    if not ids:
        return []
    by_id = {f.id: f for f in db.query(MemoryFact).filter(MemoryFact.id.in_(ids))}
    return [by_id[i] for i in ids if i in by_id]
