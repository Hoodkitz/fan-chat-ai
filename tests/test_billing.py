"""Plans: trial -> AI allowed; expired/inactive -> drafting pauses (escalation); Stripe webhook sets the plan
from the paid price (signed, exactly-once); login lockout."""
import hashlib
import hmac
import json
import time
import uuid

from app.core.config import settings
from app.core.db import new_session, set_context
from app.domain.models import Tenant
from tests.conftest import PW


def _sign(body: bytes) -> str:
    ts = int(time.time())
    mac = hmac.new(settings.STRIPE_WEBHOOK_SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def _expire_trial(tid):
    db = new_session()
    set_context(db, tid, None)
    t = db.get(Tenant, uuid.UUID(tid))
    t.trial_ends_at = t.created_at
    db.commit()
    db.close()


def test_trial_then_paused_then_paid(acc, fan, client, monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(settings, "STRIPE_PRICE_PRO", "price_pro")
    a = acc()
    assert a.get("/billing").json()["ai_enabled"] is True
    _expire_trial(a.tid)
    assert a.get("/billing").json()["ai_enabled"] is False
    f = fan(a)
    a.post(f"/fans/{f['id']}/messages", json={"direction": "in", "body": "Hallo!"})
    d = [x for x in a.get("/drafts").json() if x["fan_id"] == f["id"]][0]
    assert d["status"] == "escalated" and "pausiert" in d["escalation_reason"]

    ev = {"id": "evt_" + uuid.uuid4().hex, "type": "customer.subscription.updated", "created": 2000,
          "data": {"object": {"customer": "cus_1", "status": "active", "metadata": {"tenant_id": a.tid},
                              "items": {"data": [{"price": {"id": "price_pro"}}]}}}}
    body = json.dumps(ev).encode()
    assert client.post("/billing/webhook", content=body, headers={"Stripe-Signature": "t=1,v1=x"}).status_code == 400
    assert client.post("/billing/webhook", content=body, headers={"Stripe-Signature": _sign(body)}).status_code == 200
    assert client.post("/billing/webhook", content=body,
                       headers={"Stripe-Signature": _sign(body)}).json() == {"duplicate": True}
    st = a.get("/billing").json()
    assert st["plan"] == "pro" and st["ai_enabled"] and st["has_subscription"]

    # a subscription whose price is not one of ours never grants a plan
    ev2 = {**ev, "id": "evt_" + uuid.uuid4().hex, "created": 3000}
    ev2["data"] = {"object": {**ev["data"]["object"], "items": {"data": [{"price": {"id": "price_other"}}]}}}
    body2 = json.dumps(ev2).encode()
    client.post("/billing/webhook", content=body2, headers={"Stripe-Signature": _sign(body2)})
    assert a.get("/billing").json()["plan"] == "inactive"
    # an older event delivered late must not overwrite newer state
    ev3 = {**ev, "id": "evt_" + uuid.uuid4().hex, "created": 1000}
    body3 = json.dumps(ev3).encode()
    client.post("/billing/webhook", content=body3, headers={"Stripe-Signature": _sign(body3)})
    assert a.get("/billing").json()["plan"] == "inactive"


def test_checkout_requires_owner_and_config(acc, monkeypatch):
    a = acc()
    assert a.post("/billing/checkout", json={"plan": "pro"}).status_code == 503
    monkeypatch.setattr(settings, "STRIPE_PRICE_PRO", "price_pro")
    from app.services import billing
    monkeypatch.setattr(billing, "stripe_post", lambda path, form: {"url": "https://checkout.stripe.com/x"})
    assert a.post("/billing/checkout", json={"plan": "pro"}).json()["url"].startswith("https://checkout.stripe.com/")
    assert a.post("/billing/portal").status_code == 404


def test_login_lockout(client):
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    client.post("/auth/register", json={"email": email, "password": PW, "display_name": "L"})
    for _ in range(5):
        assert client.post("/auth/login", json={"email": email, "password": "Wrong12345x"}).status_code == 401
    assert client.post("/auth/login", json={"email": email, "password": PW}).status_code == 401  # locked, uniform answer
    ghost = client.post("/auth/login", json={"email": "nobody@example.com", "password": PW})
    assert ghost.status_code == 401 and ghost.json()["detail"] == "E-Mail oder Passwort falsch"


def test_lock_expires_and_counter_restarts(client):
    from datetime import timedelta
    from sqlalchemy import func, update
    from app.domain.models import User
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    client.post("/auth/register", json={"email": email, "password": PW, "display_name": "L"})
    for _ in range(5):
        client.post("/auth/login", json={"email": email, "password": "Wrong12345x"})
    db = new_session()
    db.execute(update(User).where(User.email == email).values(locked_until=func.now() - timedelta(seconds=1)))
    db.commit(); db.close()
    assert client.post("/auth/login", json={"email": email, "password": "Wrong12345x"}).status_code == 401
    assert client.post("/auth/login", json={"email": email, "password": PW}).status_code == 200
