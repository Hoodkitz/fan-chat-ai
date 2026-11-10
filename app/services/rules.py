"""Escalation and boundary rules: decide when the AI must NOT draft and the creator must answer personally."""
from __future__ import annotations

from decimal import Decimal

DEFAULT_ESCALATION = ["treffen", "meet", "adresse", "address", "telefonnummer", "phone", "selbstmord", "suicide",
                      "minderjährig", "underage", "polizei", "police", "anwalt", "lawyer", "erpress", "blackmail",
                      "bist du echt", "are you real", "bist du ein bot", "are you a bot", "ki?", "ai?"]


def escalation_reason(text: str, keywords: list[str], boundaries: list[str], fan_total: Decimal,
                      threshold: Decimal) -> str | None:
    t = (text or "").lower()
    for kw in DEFAULT_ESCALATION + [k.lower() for k in keywords]:
        if kw and kw in t:
            return f"Stichwort '{kw}' – persönliche Antwort nötig"
    for b in boundaries:
        if b and b.lower() in t:
            return f"Grenze berührt: '{b}'"
    if fan_total >= threshold:
        return f"Top-Fan (Umsatz {fan_total}) – persönliche Betreuung"
    return None
