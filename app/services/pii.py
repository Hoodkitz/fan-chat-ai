"""PII redaction before anything reaches the retrieval index or an LLM prompt.

Vectors can be inverted back to text, so personal identifiers of fans (phone numbers,
e-mail addresses, bank/card numbers) are replaced by placeholders first.
"""
from __future__ import annotations

import re

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?\b")
CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
PHONE_RE = re.compile(r"(?<![\w/])(?:\+|00)?\d[\d\s()./-]{6,}\d(?![\w/])")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def redact(text: str) -> tuple[str, dict[str, int]]:
    """Return (redacted text, counts per category)."""
    counts: dict[str, int] = {}

    def sub(pattern, label, s, check=None):
        def rep(m):
            if check and not check(m.group(0)):
                return m.group(0)
            counts[label] = counts.get(label, 0) + 1
            return f"<{label}>"
        return pattern.sub(rep, s)

    t = text or ""
    t = sub(EMAIL_RE, "EMAIL", t)
    t = sub(IBAN_RE, "IBAN", t)
    t = sub(CARD_RE, "CARD", t, check=lambda s: _luhn_ok(re.sub(r"\D", "", s)))
    t = sub(PHONE_RE, "PHONE", t, check=lambda s: 7 <= len(re.sub(r"\D", "", s)) <= 15)
    return t, counts
