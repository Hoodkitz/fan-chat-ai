"""Learn the creator's writing style from her own past messages (deterministic statistics)."""
from __future__ import annotations

import re
from collections import Counter

EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
WORD_RE = re.compile(r"[A-Za-zÄÖÜäöüß']+")
FORMAL = {"sie", "ihnen", "ihr", "ihre"}
INFORMAL = {"du", "dich", "dir", "dein", "deine"}


def analyze_style(messages: list[str]) -> dict:
    msgs = [m for m in messages if m and m.strip()]
    if not msgs:
        return {"samples": 0}
    words = [w.lower() for m in msgs for w in WORD_RE.findall(m)]
    emojis = Counter(e for m in msgs for e in EMOJI_RE.findall(m))
    counts = Counter(words)
    formal, informal = sum(counts[w] for w in FORMAL), sum(counts[w] for w in INFORMAL)
    common = [w for w, _ in counts.most_common(60) if len(w) > 3][:15]
    return {
        "samples": len(msgs),
        "avg_length": round(sum(len(m) for m in msgs) / len(msgs)),
        "emoji_per_message": round(sum(emojis.values()) / len(msgs), 2),
        "top_emojis": [e for e, _ in emojis.most_common(5)],
        "address": "formal" if formal > informal else "informal",
        "exclamation_rate": round(sum(m.count("!") for m in msgs) / len(msgs), 2),
        "lowercase_start_rate": round(sum(1 for m in msgs if m.strip()[0].islower()) / len(msgs), 2),
        "frequent_words": common,
        "examples": msgs[-5:],
    }
