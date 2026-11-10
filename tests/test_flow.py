from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text


def test_incoming_message_creates_pending_draft(acc, fan):
    a = acc()
    f = fan(a)
    r = a.post(f"/fans/{f['id']}/messages", json={"direction": "in", "body": "Hey, wie war dein Tag?"})
    d = r.json()["draft"]
    assert d["status"] == "pending" and d["body"]


def test_nothing_is_sent_without_approval(acc, fan):
    a = acc()
    f = fan(a)
    d = a.post(f"/fans/{f['id']}/messages", json={"direction": "in", "body": "Hallo"}).json()["draft"]
    assert a.post(f"/drafts/{d['id']}/send").status_code == 409
    assert a.post(f"/drafts/{d['id']}/decision", json={"approve": True}).status_code == 200
    r = a.post(f"/drafts/{d['id']}/send").json()
    assert r["status"] == "sent" and "KI-unterstützte Nachricht" in r["text"] and "Mia" in r["text"]
    msgs = a.get(f"/fans/{f['id']}").json()["messages"]
    assert msgs[-1]["ai_assisted"] is True
    assert a.post(f"/drafts/{d['id']}/send").status_code == 409  # no double send


def test_rejected_draft_cannot_be_sent(acc, fan):
    a = acc()
    f = fan(a)
    d = a.post(f"/fans/{f['id']}/messages", json={"direction": "in", "body": "Hallo"}).json()["draft"]
    a.post(f"/drafts/{d['id']}/decision", json={"approve": False})
    assert a.post(f"/drafts/{d['id']}/send").status_code == 409


def test_escalation_for_bot_question_and_meetings(acc, fan):
    a = acc()
    f = fan(a)
    for txt in ["Bist du ein Bot?", "Können wir uns treffen?", "Gib mir deine Adresse"]:
        d = a.post(f"/fans/{f['id']}/messages", json={"direction": "in", "body": txt}).json()["draft"]
        assert d["status"] == "escalated" and d["body"] is None
    # escalations need the creator's own words, and are sent without AI label
    assert a.post(f"/drafts/{d['id']}/decision", json={"approve": True}).status_code == 422
    a.post(f"/drafts/{d['id']}/decision", json={"approve": True, "body": "Sorry, privat bleibt privat 💕"})
    r = a.post(f"/drafts/{d['id']}/send").json()
    assert "KI" not in r["text"]


def test_boundaries_and_top_fans_escalate(acc, fan):
    a = acc()
    a.put("/profile", json={"boundaries": ["Fußfotos"], "high_value_threshold": 200})
    f = fan(a)
    d = a.post(f"/fans/{f['id']}/messages", json={"direction": "in", "body": "Machst du Fußfotos?"}).json()["draft"]
    assert d["status"] == "escalated"
    vip = fan(a)
    a.post(f"/fans/{vip['id']}/purchases", json={"item": "Video", "amount": "250.00"})
    d = a.post(f"/fans/{vip['id']}/messages", json={"direction": "in", "body": "Hi"}).json()["draft"]
    assert d["status"] == "escalated" and "Top-Fan" in d["escalation_reason"]


def test_assistant_cannot_approve(acc, fan, client):
    import uuid as _u

    from app.core.db import new_session
    from app.core.password import hash_password
    from app.domain.models import Membership, User
    from tests.conftest import PW

    a = acc()
    f = fan(a)
    d = a.post(f"/fans/{f['id']}/messages", json={"direction": "in", "body": "Hallo"}).json()["draft"]
    email = f"{_u.uuid4().hex[:8]}@example.com"
    db = new_session(a.tid)
    u = User(id=_u.uuid4(), email=email, hashed_password=hash_password(PW))
    db.add(u)
    db.flush()
    db.add(Membership(tenant_id=_u.UUID(a.tid), user_id=u.id, role="assistant"))
    db.commit()
    db.close()
    tok = client.post("/auth/login", json={"email": email, "password": PW}).json()["access_token"]
    h = {"Authorization": "Bearer " + tok}
    assert client.post(f"/drafts/{d['id']}/decision", headers=h, json={"approve": True}).status_code == 403
    assert client.get("/drafts", headers=h).status_code == 200


def test_style_learning(acc, fan):
    a = acc()
    f = fan(a)
    for t in ["hey süßer 😘 wie gehts dir?", "danke dir!! 😘😘", "hab heute neue fotos gemacht 📸"]:
        a.post(f"/fans/{f['id']}/messages", json={"direction": "out", "body": t})
    s = a.post("/profile/learn-style").json()
    assert s["samples"] == 3 and "😘" in s["top_emojis"] and s["address"] == "informal"


def test_outreach_birthday_and_inactive(acc, fan):
    a = acc()
    today = date.today()
    fan(a, birthday=today.replace(year=1995).isoformat())
    quiet = fan(a, nickname="Quiet")
    a.post(f"/fans/{quiet['id']}/messages", json={"direction": "out", "body": "hi",
                                                  "sent_at": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()})
    fan(a, nickname="NoContact", do_not_contact=True)
    drafts = a.post("/outreach/generate").json()
    reasons = sorted(d["reason"] for d in drafts)
    assert len(drafts) == 2 and "Geburtstag" in reasons
    assert a.post("/outreach/generate").json() == []  # no duplicates while pending


def test_tenant_isolation(acc, fan):
    a, b = acc("A"), acc("B")
    f = fan(a)
    d = a.post(f"/fans/{f['id']}/messages", json={"direction": "in", "body": "Hallo"}).json()["draft"]
    assert b.get(f"/fans/{f['id']}").status_code == 404
    assert b.get("/fans").json() == []
    assert b.post(f"/drafts/{d['id']}/decision", json={"approve": True}).status_code == 404
    assert b.get("/drafts").json() == []


def test_sensitive_fields_encrypted_at_rest(acc, fan):
    from app.core.db import new_session

    a = acc()
    fan(a, real_name="Thomas Geheim", preferences="mag Katzen")
    db = new_session(a.tid)
    raw = db.execute(text("SELECT real_name, preferences FROM fans")).one()
    db.close()
    assert "Geheim" not in raw[0] and "Katzen" not in raw[1]


def test_rls_default_deny_and_app_role():
    from app.core.db import new_session

    db = new_session()
    try:
        assert db.execute(text("SELECT count(*) FROM fans")).scalar() == 0
        su, bypass = db.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")).one()
        assert not su and not bypass
    finally:
        db.close()


def test_delete_fan_removes_everything(acc, fan):
    a = acc()
    f = fan(a)
    a.post(f"/fans/{f['id']}/messages", json={"direction": "in", "body": "Hallo"})
    assert a.delete(f"/fans/{f['id']}").status_code == 204
    assert a.get("/drafts").json() == [] and a.get(f"/fans/{f['id']}").status_code == 404


def test_prompt_contains_guardrails(acc, fan):
    from app.services import llm

    seen = {}

    class Spy(llm.LLM):
        def draft(self, prompt):
            seen["p"] = prompt
            return "ok"

    llm.set_llm(Spy())
    try:
        a = acc()
        a.put("/profile", json={"boundaries": ["Treffen"], "persona": "liebt Yoga"})
        f = fan(a, preferences="Yoga")
        a.post(f"/fans/{f['id']}/messages", json={"direction": "in", "body": "Was machst du heute?"})
        assert "Behaupte niemals, ein Mensch zu" in seen["p"] and "liebt Yoga" in seen["p"]
    finally:
        llm.set_llm(llm.FakeLLM())
