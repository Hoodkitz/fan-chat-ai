"""Long-term memory: durable facts about a fan, extracted from chats (PII-redacted) and
retrievable by hybrid search. Deleting the fan deletes the facts (cascade)."""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.domain.models import MemoryFact
from app.services.pii import redact
from app.services.retrieval import get_embedding

MAX_FACT_CHARS = 300
FACT_PATTERNS = [
    re.compile(r"\b(ich (?:mag|liebe|hasse|bin|habe|arbeite|wohne|komme)[^.!?\n]{3,120})", re.IGNORECASE),
    re.compile(r"\b(mein(?:e)? (?:geburtstag|hobby|lieblings\w+|frau|freundin|job|hund|katze)[^.!?\n]{2,120})", re.IGNORECASE),
    re.compile(r"\b(i (?:love|like|hate|am|have|work|live)[^.!?\n]{3,120})", re.IGNORECASE),
]


def extract_facts(text: str) -> list[str]:
    """Rule-based fact extraction (deterministic). An LLM extractor can be plugged in later."""
    out = []
    for p in FACT_PATTERNS:
        for m in p.finditer(text or ""):
            fact = m.group(1).strip()
            if fact and fact.lower() not in (o.lower() for o in out):
                out.append(fact[:MAX_FACT_CHARS])
    return out[:5]


def add_fact(db: Session, tenant_id, fan_id, fact: str, source: str = "manual") -> MemoryFact | None:
    clean, _ = redact(fact)
    clean = clean.strip()[:MAX_FACT_CHARS]
    if not clean:
        return None
    exists = db.query(MemoryFact.id).filter(MemoryFact.fan_id == fan_id, MemoryFact.fact == clean).first()
    if exists:
        return None
    f = MemoryFact(tenant_id=tenant_id, fan_id=fan_id, fact=clean, source=source,
                   embedding=get_embedding().embed(clean))
    db.add(f)
    db.flush()
    return f


def remember_from_message(db: Session, tenant_id, fan_id, text: str) -> list[MemoryFact]:
    return [f for f in (add_fact(db, tenant_id, fan_id, x, "chat") for x in extract_facts(text)) if f]
