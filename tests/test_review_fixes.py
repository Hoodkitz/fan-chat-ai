"""Regression tests for review findings."""
from app.services.rules import escalation_reason


def test_ai_keywords_match_whole_words_only():
    assert escalation_reason("Kommst du im Mai?", [], [], 0, 1000) is None
    assert escalation_reason("Magst du Thai?", [], [], 0, 1000) is None
    assert escalation_reason("Bist du eine KI?", [], [], 0, 1000) is not None


def test_naive_import_timestamps_and_do_not_contact(acc, fan):
    a = acc()
    f = fan(a)
    r = a.post(f"/fans/{f['id']}/messages", json={"direction": "out", "body": "Hi", "sent_at": "2026-01-01T10:00:00"})
    assert r.status_code == 201, r.text
    r = a.post("/fans/import", json={"fans": [{"portal": f["portal"], "portal_user_id": f["portal_user_id"],
                                     "messages": [{"direction": "out", "body": "Hallo", "sent_at": "2026-01-02T10:00:00"}]}]})
    assert r.status_code in (200, 201), r.text
    a.c.patch(f"/fans/{f['id']}", headers=a.h, json={"do_not_contact": True})
    a.post(f"/fans/{f['id']}/messages", json={"direction": "in", "body": "Hey"})
    d = [x for x in a.get("/drafts").json() if x["fan_id"] == f["id"]]
    if d:
        r = a.post(f"/drafts/{d[0]['id']}/decision", json={"approve": True, "body": "Hallo"})
        assert r.status_code == 409


def test_fifth_login_attempt_with_correct_password(client):
    import uuid
    from tests.conftest import PW
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    client.post("/auth/register", json={"email": email, "password": PW, "display_name": "L"})
    for _ in range(4):
        client.post("/auth/login", json={"email": email, "password": "Wrong12345x"})
    assert client.post("/auth/login", json={"email": email, "password": PW}).status_code == 200
