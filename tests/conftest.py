import os
import uuid

os.environ["LLM_PROVIDER"] = "fake"
os.environ.setdefault("ENV", "test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402

PW = "Geheim12345"


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


class Acc:
    def __init__(self, client, data):
        self.c, self.h, self.tid = client, {"Authorization": "Bearer " + data["access_token"]}, data["tenant_id"]

    def get(self, u, **k):
        return self.c.get(u, headers=self.h, **k)

    def post(self, u, **k):
        return self.c.post(u, headers=self.h, **k)

    def put(self, u, **k):
        return self.c.put(u, headers=self.h, **k)

    def delete(self, u, **k):
        return self.c.delete(u, headers=self.h, **k)


@pytest.fixture
def acc(client):
    def make(name="Mia"):
        r = client.post("/auth/register", json={"email": f"{uuid.uuid4().hex[:10]}@example.com", "password": PW,
                                                "display_name": name})
        assert r.status_code == 201, r.text
        return Acc(client, r.json())
    return make


@pytest.fixture
def fan(acc):
    def make(a, **kw):
        r = a.post("/fans", json={"portal": "manual", "portal_user_id": uuid.uuid4().hex[:8], "nickname": "Tom", **kw})
        assert r.status_code == 201, r.text
        return r.json()
    return make
