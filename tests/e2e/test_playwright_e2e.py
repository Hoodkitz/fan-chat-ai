import time
import httpx
import os
import pytest
from playwright.sync_api import sync_playwright

BASE = os.getenv('BASE_URL', 'http://127.0.0.1:8000')

def register(email, password, display_name):
    r = httpx.post(BASE + '/api/v1/auth/register', json={'email': email, 'password': password, 'display_name': display_name})
    r.raise_for_status()
    return r.json()

def create_fan(token, portal='fansite', portal_user_id='fan123'):
    headers = {'Authorization': 'Bearer ' + token}
    r = httpx.post(BASE + '/api/v1/fans', json={'portal': portal, 'portal_user_id': portal_user_id, 'nickname': 'TestFan'}, headers=headers)
    r.raise_for_status()
    return r.json()

def generate_outreach(token):
    headers = {'Authorization': 'Bearer ' + token}
    r = httpx.post(BASE + '/api/v1/outreach/generate', headers=headers)
    r.raise_for_status()
    return r.json()

def test_signup_profile_and_outreach():
    email = 'e2e-test@example.com'
    password = 'S3curePass!'
    d = register(email, password, 'E2E Creator')
    token = d['access_token']
    # create a fan so outreach has candidate
    fan = create_fan(token)
    # generate outreach drafts
    drafts = generate_outreach(token)
    assert isinstance(drafts, list)
    # start playwright and load app UI using session token
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        # set sessionStorage token before navigation
        page.add_init_script("sessionStorage.setItem('fc_token', '%s');" % token)
        page.goto(BASE + '/app')
        # Wait for the app to start and show the creator name
        page.wait_for_selector('#who', timeout=5000)
        who = page.inner_text('#who')
        assert 'E2E Creator' in who
        # Check drafts in queue
        page.click('button[data-tab="queue"]')
        page.wait_for_timeout(500)
        # ensure at least one card exists
        assert page.query_selector('.card textarea') is not None
        # Check manifest and sw reachable via HTTP
        r = httpx.get(BASE + '/app/manifest.webmanifest')
        assert r.status_code == 200
        r2 = httpx.get(BASE + '/app/sw.js')
        assert r2.status_code == 200
        browser.close()
