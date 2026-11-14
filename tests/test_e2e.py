"""End-to-End Tests for Fan Chat AI.

Tests registration, login, profile management, chat draft creation and lifecycle,
PWA manifest and static web assets, as well as a full browser UI flow with Playwright.
"""
from __future__ import annotations

import os
import uuid

import httpx
import pytest

from tests.conftest import PW

try:
    from playwright.sync_api import sync_playwright

    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


def _unique_email() -> str:
    return f"e2e_{uuid.uuid4().hex[:10]}@example.com"


# ============================================================================
# 1. Registrierung E2E
# ============================================================================


def test_e2e_registration_success_and_validation(client):
    """E2E: Registration succeeds with valid data, rejects weak password, and prevents duplicates."""
    email = _unique_email()
    display_name = "E2E Creator Mia"

    # Successful registration
    res = client.post(
        "/auth/register",
        json={"email": email, "password": PW, "display_name": display_name},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert "access_token" in data
    assert "tenant_id" in data
    token = data["access_token"]
    assert isinstance(token, str) and len(token) > 20

    # Duplicate registration rejected
    dup_res = client.post(
        "/auth/register",
        json={"email": email, "password": PW, "display_name": "Another Mia"},
    )
    assert dup_res.status_code == 409
    assert "bereits registriert" in dup_res.json()["detail"]

    # Weak passwords rejected
    weak_res = client.post(
        "/auth/register",
        json={"email": _unique_email(), "password": "short", "display_name": "Short"},
    )
    assert weak_res.status_code == 422


# ============================================================================
# 2. Login E2E
# ============================================================================


def test_e2e_login_flow(client):
    """E2E: Login succeeds with correct credentials and rejects incorrect passwords or unknown users."""
    email = _unique_email()
    client.post(
        "/auth/register",
        json={"email": email, "password": PW, "display_name": "Login Test User"},
    )

    # Valid login
    login_res = client.post(
        "/auth/login",
        json={"email": email, "password": PW},
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "access_token" in login_data
    assert "tenant_id" in login_data

    # Wrong password
    bad_pw_res = client.post(
        "/auth/login",
        json={"email": email, "password": "WrongPassword99!"},
    )
    assert bad_pw_res.status_code == 401

    # Unknown user
    unknown_res = client.post(
        "/auth/login",
        json={"email": _unique_email(), "password": PW},
    )
    assert unknown_res.status_code == 401


# ============================================================================
# 3. Profil E2E
# ============================================================================


def test_e2e_profile_get_and_update(client):
    """E2E: Fetch profile, update persona, boundaries, keywords and prices, verify persistence."""
    email = _unique_email()
    reg = client.post(
        "/auth/register",
        json={"email": email, "password": PW, "display_name": "Creator Persona Test"},
    ).json()
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    # Initial profile
    get_res = client.get("/profile", headers=headers)
    assert get_res.status_code == 200
    p = get_res.json()
    assert p["display_name"] == "Creator Persona Test"
    assert p["high_value_threshold"] == 100.0

    # Update profile
    updated_payload = {
        "display_name": "Creator Persona Renamed",
        "persona": "Ich bin Musikerin aus Berlin und teile hier exklusive Einblicke.",
        "boundaries": ["Keine privaten Treffen", "Keine Nacktfotos"],
        "prices": {"custom_song": 75.0, "vip_shoutout": 25.0},
        "escalation_keywords": ["anwalt", "drohung", "rechnung"],
        "high_value_threshold": 250.0,
        "auto_outreach_days": 21,
    }
    put_res = client.put("/profile", json=updated_payload, headers=headers)
    assert put_res.status_code == 200
    up = put_res.json()
    assert up["display_name"] == "Creator Persona Renamed"
    assert up["persona"] == updated_payload["persona"]
    assert up["boundaries"] == updated_payload["boundaries"]
    assert up["prices"] == {"custom_song": 75.0, "vip_shoutout": 25.0}
    assert up["high_value_threshold"] == 250.0
    assert up["auto_outreach_days"] == 21

    # Re-fetch profile to verify database round-trip
    refetch = client.get("/profile", headers=headers).json()
    assert refetch["display_name"] == "Creator Persona Renamed"
    assert refetch["persona"] == updated_payload["persona"]
    assert refetch["prices"]["custom_song"] == 75.0


# ============================================================================
# 4. Chat-Entwurf (E2E Workflow: Fan, Incoming Message, Draft, Approval, Send)
# ============================================================================


def test_e2e_chat_draft_lifecycle(client):
    """E2E: Complete lifecycle from inbound fan message to draft generation, approval, and sending."""
    email = _unique_email()
    reg = client.post(
        "/auth/register",
        json={"email": email, "password": PW, "display_name": "Draft Tester"},
    ).json()
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    # 1. Create a fan
    fan_res = client.post(
        "/fans",
        json={
            "portal": "manual",
            "portal_user_id": f"fan_{uuid.uuid4().hex[:8]}",
            "nickname": "SuperFan Leo",
            "notes": "Liebt Gitarrensolos",
        },
        headers=headers,
    )
    assert fan_res.status_code == 201
    fan = fan_res.json()
    fan_id = fan["id"]

    # 2. Inbound message from fan triggers draft generation via LLM (LLM_PROVIDER=fake)
    msg_res = client.post(
        f"/fans/{fan_id}/messages",
        json={"direction": "in", "body": "Hallo! Wann kommt dein nächster Track raus?"},
        headers=headers,
    )
    assert msg_res.status_code == 201
    msg_data = msg_res.json()
    assert msg_data["draft"] is not None
    draft_id = msg_data["draft"]["id"]

    # 3. Query drafts list for pending drafts
    drafts_res = client.get("/drafts?status=pending", headers=headers)
    assert drafts_res.status_code == 200
    pending_drafts = drafts_res.json()
    assert any(d["id"] == draft_id for d in pending_drafts)

    draft = next(d for d in pending_drafts if d["id"] == draft_id)
    assert draft["status"] == "pending"
    assert draft["kind"] == "reply"
    assert "Danke dir für deine Nachricht" in draft["body"]

    # 4. Creator approves draft
    decision_res = client.post(
        f"/drafts/{draft_id}/decision",
        json={"approve": True},
        headers=headers,
    )
    assert decision_res.status_code == 200
    assert decision_res.json()["status"] == "approved"

    # 5. Send approved draft
    send_res = client.post(f"/drafts/{draft_id}/send", headers=headers)
    assert send_res.status_code == 200
    send_data = send_res.json()
    assert send_data["status"] == "sent"
    assert "KI-unterstützte Nachricht" in send_data["text"]

    # 6. Verify conversation history has outgoing message
    history_res = client.get(f"/fans/{fan_id}", headers=headers)
    assert history_res.status_code == 200
    history = history_res.json()["messages"]
    assert len(history) == 2
    assert history[0]["direction"] == "in"
    assert history[1]["direction"] == "out"
    assert history[1]["ai_assisted"] is True


def test_e2e_escalated_draft_requires_creator_text(client):
    """E2E: Guardrails/rules trigger escalation draft, requiring creator's manual response."""
    email = _unique_email()
    reg = client.post(
        "/auth/register",
        json={"email": email, "password": PW, "display_name": "Escalation Creator"},
    ).json()
    headers = {"Authorization": f"Bearer {reg['access_token']}"}

    # Create fan
    fan = client.post(
        "/fans",
        json={"portal": "manual", "portal_user_id": f"fan_{uuid.uuid4().hex[:8]}", "nickname": "Curious"},
        headers=headers,
    ).json()

    # Incoming message asks if bot/AI -> triggers escalation rule
    msg_res = client.post(
        f"/fans/{fan['id']}/messages",
        json={"direction": "in", "body": "Bist du eigentlich ein Bot oder eine KI?"},
        headers=headers,
    )
    assert msg_res.status_code == 201
    draft = msg_res.json()["draft"]
    assert draft["status"] == "escalated"
    assert draft["escalation_reason"] is not None

    # Approving escalation without custom body must fail with 422
    fail_decision = client.post(
        f"/drafts/{draft['id']}/decision",
        json={"approve": True},
        headers=headers,
    )
    assert fail_decision.status_code == 422

    # Approving escalation WITH custom body succeeds
    ok_decision = client.post(
        f"/drafts/{draft['id']}/decision",
        json={"approve": True, "body": "Nein, ich bin eine echte Creatorin und antworte dir selbst!"},
        headers=headers,
    )
    assert ok_decision.status_code == 200
    assert ok_decision.json()["status"] == "approved"

    # Send escalation response: no AI label because written by creator herself
    send_res = client.post(f"/drafts/{draft['id']}/send", headers=headers)
    assert send_res.status_code == 200
    assert "KI-unterstützte Nachricht" not in send_res.json()["text"]


# ============================================================================
# 5. Manifest & PWA Assets E2E
# ============================================================================


def test_e2e_manifest_and_pwa_assets(client):
    """E2E: Verify webmanifest format, service worker, icon, and app shell."""
    # Manifest
    m_res = client.get("/app/manifest.webmanifest")
    assert m_res.status_code == 200
    assert "application/manifest+json" in m_res.headers.get("content-type", "")
    manifest = m_res.json()
    assert manifest["name"] == "Fan Chat Assistent"
    assert manifest["short_name"] == "FanChat"
    assert manifest["start_url"] == "/app"
    assert manifest["display"] == "standalone"
    assert len(manifest["icons"]) > 0

    # Service Worker
    sw_res = client.get("/app/sw.js")
    assert sw_res.status_code == 200
    assert "application/javascript" in sw_res.headers.get("content-type", "")
    assert "fanchat-shell" in sw_res.text

    # Icon
    icon_res = client.get("/app/icon.svg")
    assert icon_res.status_code == 200
    assert "image/svg+xml" in icon_res.headers.get("content-type", "")

    # Web App Shell
    app_res = client.get("/app")
    assert app_res.status_code == 200
    assert "text/html" in app_res.headers.get("content-type", "")
    assert "<title>Fan Chat Assistent</title>" in app_res.text
    assert 'href="/app/manifest.webmanifest"' in app_res.text


# ============================================================================
# 6. Playwright Browser E2E Flow (Optional / Local / CI skip)
# ============================================================================


def _is_live_server_reachable(url: str) -> bool:
    try:
        r = httpx.get(f"{url}/healthz", timeout=1.0)
        return r.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


@pytest.mark.skipif(not HAS_PLAYWRIGHT, reason="Playwright is not installed")
def test_e2e_playwright_browser_flow():
    """E2E Browser Test: Executes the full UI workflow in headless Chromium.

    Tests registration, profile configuration, fan creation, message entry,
    draft queue display, draft approval, and logout/login.
    """
    base_url = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8000")
    if not _is_live_server_reachable(base_url):
        pytest.skip(f"Live server not running at {base_url}")

    unique = uuid.uuid4().hex[:8]
    email = f"playwright_{unique}@example.com"
    creator_name = f"Browser Creator {unique}"
    fan_id = f"pwfan_{unique}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Load web app
        page.goto(f"{base_url}/app")
        page.wait_for_load_state("domcontentloaded")
        assert "Fan Chat Assistent" in page.title()

        # 1. Register via UI form
        page.locator("details summary").click()
        page.fill("#regName", creator_name)
        page.fill("#regEmail", email)
        page.fill("#regPassword", PW)
        page.click('#registerForm button[type="submit"]')

        # Wait for app header to show creator name
        page.wait_for_selector("#who", timeout=6000)
        assert page.inner_text("#who") == creator_name

        # 2. Update Profile via Profile Tab
        page.click('button[data-tab="profile"]')
        page.wait_for_selector("#pPersona", timeout=5000)
        page.fill("#pPersona", "E2E automated browser persona.")
        page.click('#profileForm button[type="submit"]')
        page.wait_for_timeout(500)

        # 3. Create Fan and Inbound Message via Fans Tab
        page.click('button[data-tab="fans"]')
        page.wait_for_selector('summary:has-text("Fan anlegen")', timeout=5000)
        page.click('summary:has-text("Fan anlegen")')
        page.fill("#fanPid", fan_id)
        page.fill("#fanNick", f"Fan {unique}")
        page.click('#fanForm button[type="submit"]')
        page.wait_for_selector(f"#msgFan option:has-text('Fan {unique}')", state="attached", timeout=5000)

        # Add inbound message to generate draft
        page.click('summary:has-text("Nachricht eines Fans eintragen")')
        page.fill("#msgBody", "Hallo aus dem Playwright Browser Test!")
        page.click('#msgForm button[type="submit"]')
        page.wait_for_timeout(600)

        # 4. Review and Approve Draft in Queue Tab
        page.click('button[data-tab="queue"]')
        page.wait_for_selector(".card textarea", timeout=5000)
        draft_text = page.input_value(".card textarea")
        assert "Danke dir für deine Nachricht" in draft_text

        # Approve draft (card gets removed on approval)
        page.click('button[data-act="approve"]')
        page.wait_for_selector("button[data-act='approve']", state="detached", timeout=5000)

        # 5. Logout and Login via UI
        page.click("#logout")
        page.wait_for_selector("#login:not(.hidden)", timeout=5000)

        page.fill("#email", email)
        page.fill("#password", PW)
        page.click('#loginForm button[type="submit"]')

        page.wait_for_selector("#who", timeout=5000)
        assert page.inner_text("#who") == creator_name

        browser.close()
