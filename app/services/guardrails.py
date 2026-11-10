"""Input and output rails (defence in depth against indirect prompt injection).

Input rail: fan text, nicknames and profile texts are untrusted data. Instruction-like
patterns are flagged; the message is then escalated instead of drafted.
Output rail: a draft must not contain links, contact details, claims of being human,
or free content promises. Violations block the draft (escalated to the creator).
"""
from __future__ import annotations

import re

INJECTION_PATTERNS = [
    r"ignor(e|iere)\s+(all|alle|previous|vorherige|bisherige)",
    r"(vergiss|forget)\s+(alle|all|deine|your)\s+(regeln|rules|anweisungen|instructions)",
    r"system\s*prompt", r"\bdu bist jetzt\b", r"\byou are now\b", r"\bact as\b", r"\bverhalte dich als\b",
    r"neue\s+anweisung", r"new\s+instruction", r"developer\s+mode", r"\bjailbreak\b",
    r"(sende|schick|send)\s+(mir|me)\s+.{0,30}(link|passwort|password|gratis|kostenlos|free)",
    r"<\s*/?\s*(system|instruction|untrusted)\s*>",
]
_INJ = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

URL_RE = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)
HUMAN_CLAIM_RE = re.compile(r"(ich bin (ein|eine)? ?(echter? )?mensch|bin kein bot|i am (a )?human|not a bot|keine ki)", re.IGNORECASE)
FREEBIE_RE = re.compile(r"\b(kostenlos|gratis|umsonst|for free|free of charge)\b", re.IGNORECASE)
CONTACT_RE = re.compile(r"(whatsapp|telegram|signal|snap(chat)?|instagram|insta|meine nummer|my number|\+\d{6,})", re.IGNORECASE)


def input_violations(*texts: str) -> list[str]:
    found = []
    for t in texts:
        for p in _INJ:
            if t and p.search(t):
                found.append(f"Injektionsmuster '{p.pattern[:30]}'")
                break
    return found


def output_violations(draft: str, allow_contact: bool = False) -> list[str]:
    d = draft or ""
    out = []
    if URL_RE.search(d):
        out.append("Link im Entwurf")
    if HUMAN_CLAIM_RE.search(d):
        out.append("Behauptung, ein Mensch zu sein")
    if FREEBIE_RE.search(d):
        out.append("Gratis-Versprechen")
    if not allow_contact and CONTACT_RE.search(d):
        out.append("Kontaktdaten/Plattformwechsel")
    return out


def wrap_untrusted(label: str, text: str) -> str:
    """Mark data segments so the model treats them as content, never as instructions."""
    clean = (text or "").replace("<", "‹").replace(">", "›")  # no tag can be forged inside the block
    return f"<untrusted source=\"{label}\">\n{clean}\n</untrusted>"
