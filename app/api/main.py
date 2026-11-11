"""Fan Chat AI – assistant for creators: drafts replies in her style; she decides what is sent."""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import Ctx, ctx, editor, owner
from app.core.config import settings
from app.core.db import new_session, set_context
from app.core.db import new_session as _new_session
from app.core.password import hash_password, validate_password_strength, verify_password
from app.core.tokens import create_token
from app.domain.models import (
    AuditLog,
    CreatorProfile,
    Draft,
    DraftStatus,
    Fan,
    Membership,
    MemoryFact,
    Message,
    Plan,
    Purchase,
    StripeEvent,
    Tenant,
    User,
    WebhookInbox,
)
from app.services import billing
from app.services.connectors import connector_for, export_path, sanitize_event
from app.services.drafting import create_outreach_drafts, create_reply_draft
from app.services.memory import add_fact, remember_from_message
from app.services.portals import adapter_for
from app.services.retrieval import search_facts
from app.services.style import analyze_style

app = FastAPI(title="Fan Chat AI", version="0.3.0")
MAX_FAILED_LOGINS = 5
log = logging.getLogger("fanchat.api")


def audit(c: Ctx, action: str, target: str | None = None):
    c.db.add(AuditLog(tenant_id=c.tenant_id, actor_id=c.user.id, action=action, target=target))


# ---------- auth ----------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)
    display_name: str = Field(min_length=1, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


@app.post("/auth/register", status_code=201)
def register(req: RegisterIn):
    if p := validate_password_strength(req.password):
        raise HTTPException(422, p)
    db = new_session()
    try:
        if db.query(User.id).filter(User.email == req.email.lower()).first():
            raise HTTPException(409, "E-Mail ist bereits registriert")
        user = User(id=uuid.uuid4(), email=req.email.lower(), hashed_password=hash_password(req.password))
        db.add(user)
        db.flush()
        tid = uuid.uuid4()
        set_context(db, tid, user.id)
        db.add(Tenant(id=tid, name=req.display_name))
        db.flush()
        db.add(Membership(tenant_id=tid, user_id=user.id, role="owner"))
        db.add(CreatorProfile(tenant_id=tid, display_name=req.display_name, boundaries=[], prices={},
                              escalation_keywords=[]))
        db.commit()
        return {"access_token": create_token(user.id, tid, 0), "tenant_id": str(tid)}
    finally:
        db.close()


@app.post("/auth/login")
def login(req: LoginIn):
    db = new_session()
    try:
        user = db.query(User).filter(User.email == req.email.lower()).one_or_none()
        now = datetime.now(timezone.utc)
        if user is not None and user.locked_until and user.locked_until > now:
            raise HTTPException(429, "Zu viele Fehlversuche – Konto für 15 Minuten gesperrt")
        if not verify_password(req.password, user.hashed_password if user else None):
            if user is not None:  # atomic: parallel guesses cannot share one counter value
                n = db.execute(update(User).where(User.id == user.id).values(failed_logins=User.failed_logins + 1)
                               .returning(User.failed_logins)).scalar_one()
                if n >= MAX_FAILED_LOGINS:
                    db.execute(update(User).where(User.id == user.id)
                               .values(failed_logins=0, locked_until=now + timedelta(minutes=15)))
                db.commit()
            raise HTTPException(401, "E-Mail oder Passwort falsch")
        if user.failed_logins or user.locked_until:
            user.failed_logins, user.locked_until = 0, None
            db.commit()
        set_context(db, None, user.id)
        m = db.query(Membership).filter(Membership.user_id == user.id).first()
        if m is None:
            raise HTTPException(403, "Kein Konto zugeordnet")
        return {"access_token": create_token(user.id, m.tenant_id, user.token_version), "tenant_id": str(m.tenant_id)}
    finally:
        db.close()


# ---------- creator profile ----------
class ProfileIn(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=120)
    persona: Optional[str] = Field(default=None, max_length=5000)
    boundaries: Optional[list[str]] = None
    prices: Optional[dict[str, float]] = None
    escalation_keywords: Optional[list[str]] = None
    high_value_threshold: Optional[float] = Field(default=None, ge=0)
    auto_outreach_days: Optional[int] = Field(default=None, ge=1, le=365)


def _profile_out(p: CreatorProfile) -> dict:
    return {"display_name": p.display_name, "persona": p.persona, "boundaries": p.boundaries, "prices": p.prices,
            "escalation_keywords": p.escalation_keywords, "high_value_threshold": float(p.high_value_threshold),
            "auto_outreach_days": p.auto_outreach_days, "style": p.style}


@app.get("/profile")
def get_profile(c: Ctx = Depends(ctx)):
    return _profile_out(c.db.get(CreatorProfile, c.tenant_id))


@app.put("/profile")
def put_profile(req: ProfileIn, c: Ctx = Depends(owner)):
    p = c.db.get(CreatorProfile, c.tenant_id)
    for k, v in req.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    audit(c, "profile.updated")
    return _profile_out(p)


@app.post("/profile/learn-style")
def learn_style(c: Ctx = Depends(owner)):
    """Derive the writing style from the creator's own sent messages."""
    texts = [m.body for m in c.db.query(Message).filter(Message.tenant_id == c.tenant_id, Message.direction == "out",
                                                        Message.ai_assisted.is_(False)).order_by(Message.sent_at)]
    p = c.db.get(CreatorProfile, c.tenant_id)
    p.style = analyze_style(texts[-500:])
    audit(c, "profile.style_learned")
    return p.style


# ---------- fans ----------
class FanIn(BaseModel):
    portal: str = Field(min_length=1, max_length=40)
    portal_user_id: str = Field(min_length=1, max_length=200)
    nickname: Optional[str] = Field(default=None, max_length=120)
    real_name: Optional[str] = Field(default=None, max_length=200)
    preferences: Optional[str] = Field(default=None, max_length=3000)
    notes: Optional[str] = Field(default=None, max_length=3000)
    birthday: Optional[date] = None
    do_not_contact: bool = False


def _fan_out(f: Fan) -> dict:
    return {"id": str(f.id), "portal": f.portal, "portal_user_id": f.portal_user_id, "nickname": f.nickname,
            "real_name": f.real_name, "preferences": f.preferences, "notes": f.notes,
            "birthday": f.birthday, "total_spent": float(f.total_spent or 0), "last_contact_at": f.last_contact_at,
            "do_not_contact": f.do_not_contact}


def _fan(c: Ctx, fan_id: str) -> Fan:
    try:
        f = c.db.get(Fan, uuid.UUID(fan_id))
    except ValueError:
        f = None
    if f is None:
        raise HTTPException(404, "Fan nicht gefunden")
    return f


@app.post("/fans", status_code=201)
def create_fan(req: FanIn, c: Ctx = Depends(editor)):
    f = Fan(tenant_id=c.tenant_id, total_spent=0, **req.model_dump())
    c.db.add(f)
    c.db.flush()
    return _fan_out(f)


@app.get("/fans")
def list_fans(c: Ctx = Depends(ctx)):
    return [_fan_out(f) for f in c.db.query(Fan).filter(Fan.tenant_id == c.tenant_id).order_by(Fan.created_at)]


@app.get("/fans/{fan_id}")
def get_fan(fan_id: str, c: Ctx = Depends(ctx)):
    f = _fan(c, fan_id)
    msgs = c.db.query(Message).filter(Message.fan_id == f.id).order_by(Message.sent_at).all()
    return {**_fan_out(f), "messages": [{"direction": m.direction, "body": m.body, "ai_assisted": m.ai_assisted,
                                         "sent_at": m.sent_at} for m in msgs[-100:]]}


class FanUpdate(BaseModel):
    nickname: Optional[str] = Field(default=None, max_length=120)
    real_name: Optional[str] = Field(default=None, max_length=200)
    preferences: Optional[str] = Field(default=None, max_length=3000)
    notes: Optional[str] = Field(default=None, max_length=3000)
    birthday: Optional[date] = None
    do_not_contact: Optional[bool] = None


@app.patch("/fans/{fan_id}")
def update_fan(fan_id: str, req: FanUpdate, c: Ctx = Depends(editor)):
    """Partial update. Lifting a contact block is an explicit, audited owner decision."""
    f = _fan(c, fan_id)
    data = req.model_dump(exclude_unset=True)
    if f.do_not_contact and data.get("do_not_contact") is False:
        if c.role != "owner":
            raise HTTPException(403, "Nur die Creatorin kann eine Kontaktsperre aufheben")
        audit(c, "fan.contact_block_lifted", fan_id)
    for k, v in data.items():
        setattr(f, k, v)
    return _fan_out(f)


@app.delete("/fans/{fan_id}", status_code=204)
def delete_fan(fan_id: str, c: Ctx = Depends(owner)):
    """DSGVO: hard delete of a fan incl. messages, purchases and drafts (cascade)."""
    c.db.delete(_fan(c, fan_id))
    audit(c, "fan.deleted", fan_id)


class PurchaseIn(BaseModel):
    item: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


@app.post("/fans/{fan_id}/purchases", status_code=201)
def add_purchase(fan_id: str, req: PurchaseIn, c: Ctx = Depends(editor)):
    f = _fan(c, fan_id)
    c.db.add(Purchase(tenant_id=c.tenant_id, fan_id=f.id, item=req.item, amount=req.amount))
    f.total_spent = (f.total_spent or 0) + req.amount
    return _fan_out(f)


class MessageIn(BaseModel):
    direction: Literal["in", "out"]
    body: str = Field(min_length=1, max_length=5000)
    sent_at: Optional[datetime] = None
    create_draft: bool = True


@app.post("/fans/{fan_id}/messages", status_code=201)
def add_message(fan_id: str, req: MessageIn, c: Ctx = Depends(editor)):
    """Import a chat message. An incoming message creates a reply draft (or an escalation)."""
    f = _fan(c, fan_id)
    m = Message(tenant_id=c.tenant_id, fan_id=f.id, direction=req.direction, body=req.body, ai_assisted=False)
    if req.sent_at:
        m.sent_at = req.sent_at
    c.db.add(m)
    c.db.flush()
    draft = None
    if req.direction == "in":
        remember_from_message(c.db, c.tenant_id, f.id, req.body)
        if req.create_draft:
            draft = _draft_out(create_reply_draft(c.db, c.tenant_id, f, req.body))
    else:
        f.last_contact_at = req.sent_at or datetime.now(timezone.utc)
    return {"message_id": m.id, "draft": draft}


# ---------- long-term memory ----------
class FactIn(BaseModel):
    fact: str = Field(min_length=2, max_length=300)


def _fact_out(x: MemoryFact) -> dict:
    return {"id": str(x.id), "fan_id": str(x.fan_id), "fact": x.fact, "source": x.source, "created_at": x.created_at}


@app.post("/fans/{fan_id}/facts", status_code=201)
def add_fan_fact(fan_id: str, req: FactIn, c: Ctx = Depends(editor)):
    f = _fan(c, fan_id)
    x = add_fact(c.db, c.tenant_id, f.id, req.fact, "manual")
    if x is None:
        raise HTTPException(409, "Fakt existiert bereits oder ist leer nach PII-Redaktion")
    return _fact_out(x)


@app.get("/fans/{fan_id}/facts")
def list_fan_facts(fan_id: str, q: Optional[str] = None, c: Ctx = Depends(ctx)):
    f = _fan(c, fan_id)
    if q:
        return [_fact_out(x) for x in search_facts(c.db, f.id, q, limit=10)]
    return [_fact_out(x) for x in c.db.query(MemoryFact).filter(MemoryFact.fan_id == f.id).order_by(MemoryFact.created_at)]


@app.delete("/fans/{fan_id}/facts/{fact_id}", status_code=204)
def delete_fan_fact(fan_id: str, fact_id: str, c: Ctx = Depends(editor)):
    f = _fan(c, fan_id)
    try:
        x = c.db.get(MemoryFact, uuid.UUID(fact_id))
    except ValueError:
        x = None
    if x is None or x.fan_id != f.id:
        raise HTTPException(404, "Fakt nicht gefunden")
    c.db.delete(x)


# ---------- portal inbox: official webhooks / exports only ----------
class InboundEvent(BaseModel):
    portal: str = Field(min_length=1, max_length=40)
    event_id: str = Field(min_length=1, max_length=200)
    portal_user_id: str = Field(min_length=1, max_length=200)
    nickname: Optional[str] = Field(default=None, max_length=120)
    text: str = Field(min_length=1, max_length=5000)
    sent_at: Optional[datetime] = None


def _ingest_event(db, tenant_id, ev: InboundEvent) -> dict:
    """Exactly-once processing: the inbox row is the lock; a duplicate event id is acknowledged."""
    inbox = WebhookInbox(tenant_id=tenant_id, portal=ev.portal, event_id=ev.event_id)
    try:
        with db.begin_nested():
            db.add(inbox)
            db.flush()
    except IntegrityError:
        return {"duplicate": True, "event_id": ev.event_id}
    fan = db.query(Fan).filter(Fan.tenant_id == tenant_id, Fan.portal == ev.portal,
                               Fan.portal_user_id == ev.portal_user_id).one_or_none()
    if fan is None:
        fan = Fan(tenant_id=tenant_id, portal=ev.portal, portal_user_id=ev.portal_user_id, nickname=ev.nickname,
                  total_spent=0)
        db.add(fan)
        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError:  # concurrent event created the fan first
            fan = db.query(Fan).filter(Fan.tenant_id == tenant_id, Fan.portal == ev.portal,
                                       Fan.portal_user_id == ev.portal_user_id).one()
    m = Message(tenant_id=tenant_id, fan_id=fan.id, direction="in", body=ev.text, ai_assisted=False)
    if ev.sent_at:
        m.sent_at = ev.sent_at
    db.add(m)
    db.flush()
    remember_from_message(db, tenant_id, fan.id, ev.text)
    d = create_reply_draft(db, tenant_id, fan, ev.text)
    inbox.processed_at = datetime.now(timezone.utc)
    return {"duplicate": False, "event_id": ev.event_id, "fan_id": str(fan.id), "draft": _draft_out(d)}


@app.post("/inbox/events")
def inbox_event(ev: InboundEvent, c: Ctx = Depends(editor)):
    """Authenticated ingestion (e.g. from a connector that polls an official portal API)."""
    return _ingest_event(c.db, c.tenant_id, ev)


@app.post("/profile/webhook-secret")
def rotate_webhook_secret(c: Ctx = Depends(owner)):
    p = c.db.get(CreatorProfile, c.tenant_id)
    p.webhook_secret = secrets.token_urlsafe(32)
    audit(c, "profile.webhook_secret_rotated")
    return {"webhook_url": f"/webhooks/{c.tenant_id}", "secret": p.webhook_secret}


@app.post("/webhooks/{tenant_id}")
async def portal_webhook(tenant_id: str, request: Request, x_signature: str = Header(default="")):
    """Unauthenticated portal webhook, protected by HMAC-SHA256 over the raw body."""
    try:
        tid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(404, "Unbekannt")
    raw = await request.body()
    db = _new_session(tid)
    try:
        p = db.get(CreatorProfile, tid)
        if p is None or not p.webhook_secret:
            raise HTTPException(404, "Unbekannt")
        expected = hmac.new(p.webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, (x_signature or "").lower().removeprefix("sha256=")):
            raise HTTPException(401, "Signatur ungültig")
        ev = InboundEvent.model_validate_json(raw)
        out = _ingest_event(db, tid, ev)
        db.commit()
        return out
    except HTTPException:
        db.rollback()
        raise
    except ValueError as e:
        db.rollback()
        raise HTTPException(422, str(e)[:200])
    finally:
        db.close()


# ---------- connectors (official portal APIs / exports, polled) ----------
class ConnectorIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: str = Field(min_length=1, max_length=40)
    portal: str = Field(min_length=1, max_length=40)
    config: dict = Field(default_factory=dict)


def _load_connectors(p: CreatorProfile) -> list[dict]:
    import json
    return json.loads(p.connectors) if p.connectors else []


def _save_connectors(p: CreatorProfile, items: list[dict]) -> None:
    import json
    p.connectors = json.dumps(items)


def _connector_out(c: dict) -> dict:
    return {"name": c["name"], "kind": c["kind"], "portal": c["portal"], "cursor": c.get("cursor"),
            "config_keys": sorted(c.get("config", {}).keys())}


@app.get("/connectors")
def list_connectors(c: Ctx = Depends(owner)):
    return [_connector_out(x) for x in _load_connectors(c.db.get(CreatorProfile, c.tenant_id))]


@app.put("/connectors/{name}", status_code=201)
def put_connector(name: str, req: ConnectorIn, c: Ctx = Depends(owner)):
    if connector_for(req.kind) is None:
        raise HTTPException(422, f"Unbekannter Connector-Typ '{req.kind}'")
    p = c.db.get(CreatorProfile, c.tenant_id)
    items = [x for x in _load_connectors(p) if x["name"] != name]
    items.append({"name": name, "kind": req.kind, "portal": req.portal, "config": req.config, "cursor": None})
    _save_connectors(p, items)
    audit(c, "connector.saved", name)
    return _connector_out(items[-1])


@app.delete("/connectors/{name}", status_code=204)
def delete_connector(name: str, c: Ctx = Depends(owner)):
    p = c.db.get(CreatorProfile, c.tenant_id)
    _save_connectors(p, [x for x in _load_connectors(p) if x["name"] != name])
    audit(c, "connector.deleted", name)


@app.put("/connectors/{name}/export", status_code=201)
def upload_export(name: str, data: list[dict], c: Ctx = Depends(owner)):
    """Store an official portal data export (JSON list) for the export_file connector of this tenant."""
    import json
    if len(data) > 20000:
        raise HTTPException(413, "Maximal 20000 Einträge pro Export")
    try:
        path = export_path(c.tenant_id, name)
    except ValueError:
        raise HTTPException(422, "Ungültiger Connector-Name")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    audit(c, "connector.export_uploaded", name)
    return {"name": name, "entries": len(data)}


@app.post("/connectors/poll")
def poll_connectors(c: Ctx = Depends(editor)):
    """One poll cycle over all configured connectors; new messages become drafts via the idempotent inbox.
    The profile row is locked for the read-modify-write of the cursors."""
    p = c.db.get(CreatorProfile, c.tenant_id, with_for_update=True)
    items = _load_connectors(p)
    report = []
    for item in items:
        conn = connector_for(item["kind"])
        if conn is None:
            report.append({"name": item["name"], "error": "connector_unavailable"})
            continue
        cfg = {**item.get("config", {}), "_tenant_id": str(c.tenant_id), "_name": item["name"], "_portal": item["portal"]}
        try:
            events, cursor = conn.poll(cfg, item.get("cursor"))
        except Exception:  # a broken portal must not stop the others; details only in the server log
            log.exception("connector %s failed (tenant %s)", item["name"], c.tenant_id)
            report.append({"name": item["name"], "error": "poll_failed"})
            continue
        new = dup = 0
        for ev in events:
            ev = sanitize_event(ev)
            out = _ingest_event(c.db, c.tenant_id, InboundEvent(
                portal=ev.portal or item["portal"], event_id=ev.event_id, portal_user_id=ev.portal_user_id,
                nickname=ev.nickname, text=ev.text, sent_at=ev.sent_at))
            if out["duplicate"]:
                dup += 1
            else:
                new += 1
        item["cursor"] = cursor
        report.append({"name": item["name"], "new": new, "duplicates": dup})
    _save_connectors(p, items)
    audit(c, "connectors.polled", f"{len(items)} connectors")
    return report


class ImportMessage(BaseModel):
    direction: Literal["in", "out"]
    body: str = Field(min_length=1, max_length=5000)
    sent_at: Optional[datetime] = None


class ImportFan(BaseModel):
    portal: str = Field(min_length=1, max_length=40)
    portal_user_id: str = Field(min_length=1, max_length=200)
    nickname: Optional[str] = Field(default=None, max_length=120)
    messages: list[ImportMessage] = Field(default_factory=list, max_length=2000)


class ImportIn(BaseModel):
    fans: list[ImportFan] = Field(max_length=200)


MAX_IMPORT_MESSAGES = 20000


@app.post("/fans/import")
def import_chats(req: ImportIn, c: Ctx = Depends(editor)):
    """Import of exported chat histories (official portal exports). No drafts are created.
    Re-importing the same export is idempotent: messages already present (direction, time, text) are skipped."""
    if sum(len(f.messages) for f in req.fans) > MAX_IMPORT_MESSAGES:
        raise HTTPException(413, f"Maximal {MAX_IMPORT_MESSAGES} Nachrichten pro Import")
    created_fans = created_msgs = skipped = 0
    for item in req.fans:
        fan = c.db.query(Fan).filter(Fan.tenant_id == c.tenant_id, Fan.portal == item.portal,
                                     Fan.portal_user_id == item.portal_user_id).one_or_none()
        if fan is None:
            fan = Fan(tenant_id=c.tenant_id, portal=item.portal, portal_user_id=item.portal_user_id,
                      nickname=item.nickname, total_spent=0)
            c.db.add(fan)
            c.db.flush()
            created_fans += 1
        last_out = None
        existing = {(m.direction, m.sent_at, m.body) for m in c.db.query(Message).filter(Message.fan_id == fan.id)}
        for mi in item.messages:
            if mi.sent_at and (mi.direction, mi.sent_at, mi.body) in existing:
                skipped += 1
                continue
            m = Message(tenant_id=c.tenant_id, fan_id=fan.id, direction=mi.direction, body=mi.body, ai_assisted=False)
            if mi.sent_at:
                m.sent_at = mi.sent_at
            c.db.add(m)
            created_msgs += 1
            if mi.direction == "in":
                remember_from_message(c.db, c.tenant_id, fan.id, mi.body)
            elif mi.sent_at and (last_out is None or mi.sent_at > last_out):
                last_out = mi.sent_at
        if last_out and (fan.last_contact_at is None or last_out > fan.last_contact_at):
            fan.last_contact_at = last_out
    audit(c, "fans.imported", f"{created_fans} fans, {created_msgs} messages, {skipped} skipped")
    return {"fans_created": created_fans, "messages_imported": created_msgs, "messages_skipped": skipped}


# ---------- drafts ----------
def _draft_out(d: Draft) -> dict:
    return {"id": str(d.id), "fan_id": str(d.fan_id), "kind": d.kind, "reason": d.reason, "body": d.body,
            "status": d.status, "escalation_reason": d.escalation_reason, "created_at": d.created_at}


def _draft(c: Ctx, draft_id: str, lock=False) -> Draft:
    try:
        d = c.db.get(Draft, uuid.UUID(draft_id), with_for_update=lock)
    except ValueError:
        d = None
    if d is None:
        raise HTTPException(404, "Entwurf nicht gefunden")
    return d


@app.get("/drafts")
def list_drafts(status: Optional[str] = None, c: Ctx = Depends(ctx)):
    q = c.db.query(Draft).filter(Draft.tenant_id == c.tenant_id)
    if status:
        q = q.filter(Draft.status == status)
    return [_draft_out(d) for d in q.order_by(Draft.created_at.desc()).limit(200)]


class DecisionIn(BaseModel):
    approve: bool
    body: Optional[str] = Field(default=None, min_length=1, max_length=2000)  # edited text


@app.post("/drafts/{draft_id}/decision")
def decide(draft_id: str, req: DecisionIn, c: Ctx = Depends(owner)):
    """Only the creator herself approves. Escalations need her own text (body) to be approved."""
    d = _draft(c, draft_id, lock=True)
    if d.status not in (DraftStatus.PENDING.value, DraftStatus.ESCALATED.value):
        raise HTTPException(409, f"Entwurf ist bereits {d.status}")
    if req.approve:
        if d.status == DraftStatus.ESCALATED.value and not req.body:
            raise HTTPException(422, "Eskalation: bitte eigene Antwort schreiben")
        if req.body:
            d.body = req.body
        d.status = DraftStatus.APPROVED.value
    else:
        d.status = DraftStatus.REJECTED.value
    d.decided_by, d.decided_at = c.user.id, datetime.now(timezone.utc)
    audit(c, f"draft.{d.status}", draft_id)
    return _draft_out(d)


@app.post("/drafts/{draft_id}/send")
def send(draft_id: str, c: Ctx = Depends(editor)):
    d = _draft(c, draft_id, lock=True)
    if d.status != DraftStatus.APPROVED.value:
        raise HTTPException(409, "Nur freigegebene Entwürfe können gesendet werden")
    fan = c.db.get(Fan, d.fan_id)
    if fan.do_not_contact:
        raise HTTPException(409, "Fan möchte nicht kontaktiert werden")
    profile = c.db.get(CreatorProfile, c.tenant_id)
    # Escalations were written by the creator herself -> no AI label; everything else is AI-assisted.
    ai = d.escalation_reason is None
    text = d.body + ("\n\n" + settings.AI_DISCLOSURE.format(model=profile.display_name) if ai else "")
    result = adapter_for(fan.portal).send(fan.portal_user_id, text)
    c.db.add(Message(tenant_id=c.tenant_id, fan_id=fan.id, direction="out", body=text, ai_assisted=ai))
    fan.last_contact_at = datetime.now(timezone.utc)
    d.status = DraftStatus.SENT.value
    audit(c, "draft.sent", draft_id)
    return {"status": "sent", "text": text, "delivery": result}


@app.post("/outreach/generate")
def outreach(c: Ctx = Depends(editor)):
    return [_draft_out(d) for d in create_outreach_drafts(c.db, c.tenant_id)]


@app.get("/stats")
def stats(c: Ctx = Depends(ctx)):
    q = c.db.query(Draft).filter(Draft.tenant_id == c.tenant_id)
    by = {}
    for d in q:
        by[d.status] = by.get(d.status, 0) + 1
    fans = c.db.query(Fan).filter(Fan.tenant_id == c.tenant_id).all()
    per_portal: dict[str, dict] = {}
    for f in fans:
        p = per_portal.setdefault(f.portal, {"fans": 0, "revenue": 0.0, "messages_in": 0, "messages_out": 0})
        p["fans"] += 1
        p["revenue"] += float(f.total_spent or 0)
    fan_portal = {f.id: f.portal for f in fans}
    for fan_id, direction, n in c.db.query(Message.fan_id, Message.direction, func.count()).filter(
            Message.tenant_id == c.tenant_id).group_by(Message.fan_id, Message.direction):
        p = per_portal.get(fan_portal.get(fan_id))
        if p is not None:
            p["messages_in" if direction == "in" else "messages_out"] += n
    return {"fans": len(fans), "revenue": float(sum((f.total_spent or 0) for f in fans)), "drafts": by,
            "top_fans": sorted(({"nickname": f.nickname, "total_spent": float(f.total_spent or 0)} for f in fans),
                               key=lambda x: -x["total_spent"])[:5],
            "per_portal": per_portal}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


WEB_DIR = Path(__file__).resolve().parents[1] / "web"


@app.get("/app/{asset}", include_in_schema=False)
def dashboard_asset(asset: str):
    allowed = {"manifest.webmanifest": "application/manifest+json", "icon.svg": "image/svg+xml", "sw.js": "application/javascript"}
    if asset not in allowed:
        raise HTTPException(404, "Nicht gefunden")
    return FileResponse(WEB_DIR / asset, media_type=allowed[asset], headers={"Cache-Control": "no-cache"})


@app.get("/app", include_in_schema=False)
@app.get("/", include_in_schema=False)
def dashboard():
    """Creator dashboard: approval queue, escalations, fans, stats (static page on this API)."""
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-store",
                                                         "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; manifest-src 'self'; worker-src 'self'"})


# ---------- billing ----------
class CheckoutIn(BaseModel):
    plan: Literal["pro", "agency"]


@app.get("/billing")
def billing_status(c: Ctx = Depends(ctx)):
    t = c.db.get(Tenant, c.tenant_id)
    return {"plan": t.plan, "trial_ends_at": t.trial_ends_at, "ai_enabled": billing.ai_allowed(t),
            "has_subscription": bool(t.stripe_customer_id)}


@app.post("/billing/checkout")
def billing_checkout(req: CheckoutIn, c: Ctx = Depends(owner)):
    price = {"pro": settings.STRIPE_PRICE_PRO, "agency": settings.STRIPE_PRICE_AGENCY}[req.plan]
    if not price:
        raise HTTPException(503, "Zahlungen sind noch nicht eingerichtet")
    t = c.db.get(Tenant, c.tenant_id)
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    form = [("mode", "subscription"), ("line_items[0][price]", price), ("line_items[0][quantity]", "1"),
            ("success_url", f"{base}/app/?billing=success"), ("cancel_url", f"{base}/app/?billing=cancel"),
            ("client_reference_id", str(t.id)), ("allow_promotion_codes", "true"),
            ("subscription_data[metadata][tenant_id]", str(t.id))]
    if t.stripe_customer_id:
        form.append(("customer", t.stripe_customer_id))
    try:
        return {"url": billing.stripe_post("checkout/sessions", form)["url"]}
    except billing.BillingError as e:
        raise HTTPException(502, str(e))


@app.post("/billing/portal")
def billing_portal(c: Ctx = Depends(owner)):
    t = c.db.get(Tenant, c.tenant_id)
    if not t.stripe_customer_id:
        raise HTTPException(404, "Noch kein Abo vorhanden")
    try:
        return {"url": billing.stripe_post("billing_portal/sessions", [
            ("customer", t.stripe_customer_id), ("return_url", f"{settings.PUBLIC_BASE_URL.rstrip('/')}/app/")])["url"]}
    except billing.BillingError as e:
        raise HTTPException(502, str(e))


@app.post("/billing/webhook")
async def billing_webhook(request: Request, sig: Optional[str] = Header(None, alias="Stripe-Signature")):
    body = await request.body()
    if not billing.verify_signature(body, sig):
        raise HTTPException(400, "Ungültige Signatur")
    import json
    event = json.loads(body)
    db = new_session()
    try:
        db.add(StripeEvent(event_id=str(event.get("id", ""))[:100]))
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return {"duplicate": True}
        obj = (event.get("data") or {}).get("object") or {}
        etype = event.get("type", "")
        tid = None
        if etype == "checkout.session.completed":
            tid = obj.get("client_reference_id")
        elif etype.startswith("customer.subscription."):
            tid = (obj.get("metadata") or {}).get("tenant_id")
        try:
            tid = uuid.UUID(str(tid)) if tid else None
        except ValueError:
            tid = None
        if tid is not None:
            set_context(db, tid, None)
            t = db.get(Tenant, tid)
            if t is not None:
                if obj.get("customer"):
                    t.stripe_customer_id = str(obj["customer"])[:64]
                if etype.startswith("customer.subscription."):
                    prices = [((i.get("price") or {}).get("id")) for i in ((obj.get("items") or {}).get("data") or [])]
                    plan = billing.plan_for_prices(prices)
                    active = obj.get("status") in ("active", "trialing") and etype != "customer.subscription.deleted"
                    t.plan = (plan.value if (active and plan) else Plan.INACTIVE.value)
        db.commit()
        return {"received": True}
    finally:
        db.close()
