"""Fan Chat AI – assistant for creators: drafts replies in her style; she decides what is sent."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import Ctx, ctx, editor, owner
from app.core.config import settings
from app.core.db import new_session, set_context
from app.core.password import hash_password, validate_password_strength, verify_password
from app.core.tokens import create_token
from app.domain.models import (AuditLog, CreatorProfile, Draft, DraftStatus, Fan, Membership, Message, Purchase,
                               Tenant, User)
from app.services.drafting import create_outreach_drafts, create_reply_draft
from app.services.portals import adapter_for
from app.services.style import analyze_style

app = FastAPI(title="Fan Chat AI", version="0.1.0")


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
        if not verify_password(req.password, user.hashed_password if user else None):
            raise HTTPException(401, "E-Mail oder Passwort falsch")
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


@app.patch("/fans/{fan_id}")
def update_fan(fan_id: str, req: FanIn, c: Ctx = Depends(editor)):
    f = _fan(c, fan_id)
    for k, v in req.model_dump().items():
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
    if req.direction == "in" and req.create_draft:
        draft = _draft_out(create_reply_draft(c.db, c.tenant_id, f, req.body))
    else:
        f.last_contact_at = req.sent_at or datetime.now(timezone.utc)
    return {"message_id": m.id, "draft": draft}


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
    return {"fans": len(fans), "revenue": float(sum((f.total_spent or 0) for f in fans)), "drafts": by,
            "top_fans": sorted(({"nickname": f.nickname, "total_spent": float(f.total_spent or 0)} for f in fans),
                               key=lambda x: -x["total_spent"])[:5]}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
