import time
import httpx
import os
import pytest
from playwright.sync_api import sync_playwright

BASE = os.getenv('BASE_URL', 'http://127.0.0.1:8000')

def register(email, password, display_name, client):
    r = client.post('/auth/register', json={'email': email, 'password': password, 'display_name': display_name})
    if r.status_code == 409:
        l = client.post('/auth/login', json={'email': email, 'password': password})
        l.raise_for_status()
        return l.json()
    r.raise_for_status()
    return r.json()

def create_fan(token, client, portal='fansite', portal_user_id=None):
    import uuid
    if not portal_user_id:
        portal_user_id = uuid.uuid4().hex[:8]
    headers = {'Authorization': 'Bearer ' + token}
    r = client.post('/fans', json={'portal': portal, 'portal_user_id': portal_user_id, 'nickname': 'TestFan'}, headers=headers)
    r.raise_for_status()
    return r.json()

def generate_outreach(token, client):
    headers = {'Authorization': 'Bearer ' + token}
    r = client.post('/outreach/generate', headers=headers)
    r.raise_for_status()
    return r.json()

def test_signup_profile_and_outreach():
    email = 'e2e-test@example.com'
    password = 'S3curePass!'
    from fastapi.testclient import TestClient
    from app.api.main import app
    client = TestClient(app)
    d = register(email, password, 'E2E Creator', client)
    token = d['access_token']
    # create a fan so outreach has candidate
    fan = create_fan(token, client)
    # generate outreach drafts
    drafts = generate_outreach(token, client)
    assert isinstance(drafts, list)
    # Use TestClient for lightweight UI checks (avoids external browser in CI).
    # The SPA is static; ensure index returns and assets are reachable
    r = client.get('/app')
    assert r.status_code == 200
    assert 'Fan Chat Assistent' in r.text
    r = client.get('/app/manifest.webmanifest')
    assert r.status_code == 200
    r = client.get('/app/sw.js')
    assert r.status_code == 200
    # Ensure drafts endpoint shows generated drafts for the tenant we created
    headers = {'Authorization': 'Bearer ' + token}
    r = client.get('/drafts', headers=headers)
    r.raise_for_status()
    assert isinstance(r.json(), list)
