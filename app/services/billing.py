"""Plans and Stripe: checkout/portal sessions, signed webhooks. The plan is only ever set by a verified webhook,
and derived from the price actually paid (never from client-controlled metadata)."""
from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.domain.models import Plan, Tenant

STRIPE = "https://api.stripe.com/v1"
SIG_TOLERANCE = 300


class BillingError(RuntimeError):
    pass


def ai_allowed(t: Tenant) -> bool:
    if t.plan in (Plan.PRO.value, Plan.AGENCY.value):
        return True
    if t.plan == Plan.TRIAL.value:
        return t.trial_ends_at is None or t.trial_ends_at > datetime.now(timezone.utc)
    return False


def plan_for_prices(price_ids: list[str]) -> Plan | None:
    by_price = {settings.STRIPE_PRICE_AGENCY: Plan.AGENCY, settings.STRIPE_PRICE_PRO: Plan.PRO}
    found = {by_price[p] for p in price_ids if p and p in by_price}
    for plan in (Plan.AGENCY, Plan.PRO):
        if plan in found:
            return plan
    return None


def verify_signature(payload: bytes, header: str | None) -> bool:
    """Stripe-Signature: t=<ts>,v1=<hex hmac-sha256 of 't.payload'>; rejects replays older than 5 minutes."""
    if not header or not settings.STRIPE_WEBHOOK_SECRET:
        return False
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    try:
        ts = int(parts.get("t", ""))
    except ValueError:
        return False
    if abs(time.time() - ts) > SIG_TOLERANCE:
        return False
    expected = hmac.new(settings.STRIPE_WEBHOOK_SECRET.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    sigs = [v for k, v in (p.split("=", 1) for p in header.split(",") if "=" in p) if k == "v1"]
    return any(hmac.compare_digest(expected, s) for s in sigs)


def stripe_post(path: str, form: list[tuple[str, str]]) -> dict:
    if not settings.STRIPE_SECRET_KEY:
        raise BillingError("Zahlungen sind noch nicht eingerichtet")
    try:
        r = httpx.post(f"{STRIPE}/{path}", content=urlencode(form), auth=(settings.STRIPE_SECRET_KEY, ""),
                       headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=20)
    except httpx.HTTPError:
        raise BillingError("Zahlungsanbieter nicht erreichbar")
    if r.status_code >= 400:
        raise BillingError("Zahlungsanbieter hat die Anfrage abgelehnt")
    return r.json()
