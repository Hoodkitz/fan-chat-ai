from playwright.sync_api import sync_playwright
import requests
import uuid

BASE = "http://127.0.0.1:8000"
PW = "Geheim12345"


def run():
    # register
    email = f"e2e_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(BASE + "/auth/register", json={"email": email, "password": PW, "display_name": "E2E Test"})
    r.raise_for_status()
    tok = r.json()["access_token"]

    # create a fan via API
    headers = {"Authorization": "Bearer " + tok}
    resp = requests.post(BASE + "/fans", json={"portal": "manual", "portal_user_id": "e2e1234", "nickname": "Alex"}, headers=headers)
    resp.raise_for_status()
    fan = resp.json()

    # add inbound message to create a draft
    resp = requests.post(f"{BASE}/fans/{fan['id']}/messages", json={"direction": "in", "body": "Hallo, ich mag deine Musik"}, headers=headers)
    resp.raise_for_status()

    # verify via API that a pending draft exists
    ds = requests.get(BASE + '/drafts', headers=headers).json()
    assert any(d for d in ds if d['status'] == 'pending')
    print('Drafts via API OK ->', len(ds))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # set token in sessionStorage before loading the app (not required for sw/manifest)
        page.add_init_script(f"() => sessionStorage.setItem('fc_token', '{tok}')")
        page.goto(BASE + "/app")
        # give service worker a moment to register
        page.wait_for_timeout(1500)
        # manifest and sw
        m = requests.get(BASE + '/app/manifest.webmanifest')
        assert m.status_code == 200
        sw_reg = page.evaluate('() => navigator.serviceWorker.getRegistration().then(r => !!r)')
        print('Service worker registered?', sw_reg)
        browser.close()


if __name__ == '__main__':
    run()
