"""Draft creation: RAG over creator profile, fan record and recent conversation.

The AI only ever produces drafts. Sending requires approval and always carries the
AI disclosure. Escalation cases get no AI text at all.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.domain.models import CreatorProfile, Draft, DraftStatus, Fan, Message, Purchase
from app.services.llm import get_llm
from app.services.rules import escalation_reason

MAX_DRAFT_CHARS = 1000


def _clip(s, n):
    return (s or "")[:n]


def build_prompt(profile: CreatorProfile, fan: Fan, history: list[Message], purchases: list[Purchase],
                 incoming: str | None, purpose: str) -> str:
    style = profile.style or {}
    hist = "\n".join(f"{'FAN' if m.direction == 'in' else 'ICH'}: {_clip(m.body, 400)}" for m in history[-12:])
    buys = ", ".join(f"{p.item} ({p.amount} €)" for p in purchases[-5:]) or "keine"
    return f"""Du schreibst einen ANTWORT-ENTWURF für die Creatorin "{profile.display_name}". Sie prüft und gibt
ihn selbst frei. Schreibe in ihrem Stil, in der Ich-Form, kurz und natürlich. Behaupte niemals, ein Mensch zu
sein, verabrede keine Treffen, gib keine privaten Daten heraus, und überschreite keine dieser Grenzen:
{', '.join(profile.boundaries or []) or 'keine angegeben'}.
Preise (nur nennen, wenn passend): {profile.prices or {}}

STIL: Anrede {style.get('address', 'informal')}, ~{style.get('avg_length', 120)} Zeichen,
Emojis/Nachricht {style.get('emoji_per_message', 1)}, typische Emojis {style.get('top_emojis', [])},
typische Wörter {style.get('frequent_words', [])}. Beispiele: {style.get('examples', [])}

PERSONA: {_clip(profile.persona, 800)}
FAN: {fan.nickname or 'Fan'}; Vorlieben: {_clip(fan.preferences, 300)}; Notizen: {_clip(fan.notes, 300)};
Käufe: {buys}

VERLAUF:
{hist or '(noch keiner)'}

ZWECK: {purpose}
NACHRICHT DES FANS: {_clip(incoming, 1000) or '(keine – proaktive Nachricht)'}

Gib NUR den Nachrichtentext zurück."""


def create_reply_draft(db: Session, tenant_id, fan: Fan, incoming_text: str) -> Draft:
    profile = db.get(CreatorProfile, tenant_id)
    reason = escalation_reason(incoming_text, profile.escalation_keywords or [], profile.boundaries or [],
                               fan.total_spent or 0, profile.high_value_threshold)
    if reason:
        d = Draft(tenant_id=tenant_id, fan_id=fan.id, kind="reply", status=DraftStatus.ESCALATED.value,
                  escalation_reason=reason, reason="Eskalation")
    else:
        history = (db.query(Message).filter(Message.fan_id == fan.id).order_by(Message.sent_at).all())
        purchases = db.query(Purchase).filter(Purchase.fan_id == fan.id).order_by(Purchase.purchased_at).all()
        text = get_llm().draft(build_prompt(profile, fan, history, purchases, incoming_text, "Antwort auf den Fan"))
        d = Draft(tenant_id=tenant_id, fan_id=fan.id, kind="reply", body=text[:MAX_DRAFT_CHARS],
                  status=DraftStatus.PENDING.value, reason="Antwort")
    db.add(d)
    db.flush()
    return d


def outreach_candidates(db: Session, tenant_id, today: date | None = None) -> list[tuple[Fan, str]]:
    """Fans that should hear from the creator: birthday today, or no contact for N days."""
    today = today or date.today()
    profile = db.get(CreatorProfile, tenant_id)
    cutoff = datetime.now(timezone.utc) - timedelta(days=profile.auto_outreach_days)
    out = []
    for fan in db.query(Fan).filter(Fan.tenant_id == tenant_id, Fan.do_not_contact.is_(False)):
        if fan.birthday and (fan.birthday.month, fan.birthday.day) == (today.month, today.day):
            out.append((fan, "Geburtstag"))
        elif fan.last_contact_at is None or fan.last_contact_at < cutoff:
            out.append((fan, f"seit {profile.auto_outreach_days}+ Tagen kein Kontakt"))
    return out


def create_outreach_drafts(db: Session, tenant_id, today: date | None = None) -> list[Draft]:
    profile = db.get(CreatorProfile, tenant_id)
    drafts = []
    for fan, why in outreach_candidates(db, tenant_id, today):
        open_exists = db.query(Draft.id).filter(Draft.fan_id == fan.id, Draft.kind == "outreach",
                                                Draft.status == DraftStatus.PENDING.value).first()
        if open_exists:
            continue
        history = db.query(Message).filter(Message.fan_id == fan.id).order_by(Message.sent_at).all()
        purchases = db.query(Purchase).filter(Purchase.fan_id == fan.id).all()
        text = get_llm().draft(build_prompt(profile, fan, history, purchases, None, f"Kontaktpflege: {why}"))
        d = Draft(tenant_id=tenant_id, fan_id=fan.id, kind="outreach", reason=why, body=text[:MAX_DRAFT_CHARS],
                  status=DraftStatus.PENDING.value)
        db.add(d)
        drafts.append(d)
    db.flush()
    return drafts
