"""Backend integration tests for himawari24 Netflix Email Access app."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://outlook-graph-mail.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@himawari24.app"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data
    assert data["user"]["email"] == ADMIN_EMAIL
    return data["access_token"]


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- Auth ----------
class TestAuth:
    def test_login_invalid(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"}, timeout=15)
        assert r.status_code == 401

    def test_me_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code in (401, 403)

    def test_me_ok(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_protected_no_token(self):
        for path in ["/api/assignments", "/api/mailboxes", "/api/config/status", "/api/categories"]:
            r = requests.get(f"{BASE_URL}{path}", timeout=15)
            assert r.status_code in (401, 403), f"{path} did not require auth"


# ---------- Config & Categories ----------
class TestConfig:
    def test_config_status(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/config/status", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["microsoft_configured"] is False
        assert d["gmail_configured"] is False
        assert "/api/oauth/microsoft/callback" in d["redirect_uri"]

    def test_categories(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/categories", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        cats = r.json()
        keys = {c["key"] for c in cats}
        assert keys == {"login_code", "verification_code", "household", "password_reset", "tv_login"}


# ---------- Assignments CRUD ----------
class TestAssignments:
    unique = uuid.uuid4().hex[:8]
    ol_email = f"TEST_ol_{unique}@example.com"
    gm_email = f"TEST_gm_{unique}@example.com"

    def test_create_outlook(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/assignments", headers=auth_headers,
                          json={"email": self.ol_email, "provider": "outlook_graph", "label": "test"}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["email_norm"] == self.ol_email.lower()
        assert d["provider"] == "outlook_graph"
        TestAssignments.ol_id = d["id"]

    def test_create_gmail(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/assignments", headers=auth_headers,
                          json={"email": self.gm_email, "provider": "gmail_imap"}, timeout=15)
        assert r.status_code == 200
        TestAssignments.gm_id = r.json()["id"]

    def test_duplicate_returns_409(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/assignments", headers=auth_headers,
                          json={"email": self.ol_email, "provider": "outlook_graph"}, timeout=15)
        assert r.status_code == 409

    def test_list_contains(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/assignments", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        emails = {a["email_norm"] for a in r.json()}
        assert self.ol_email.lower() in emails
        assert self.gm_email.lower() in emails

    def test_update_provider(self, auth_headers):
        r = requests.patch(f"{BASE_URL}/api/assignments/{TestAssignments.ol_id}", headers=auth_headers,
                           json={"provider": "gmail_imap"}, timeout=15)
        assert r.status_code == 200
        r2 = requests.get(f"{BASE_URL}/api/assignments", headers=auth_headers, timeout=15)
        prov = next(a["provider"] for a in r2.json() if a["id"] == TestAssignments.ol_id)
        assert prov == "gmail_imap"

    def test_invalid_provider(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/assignments", headers=auth_headers,
                          json={"email": f"TEST_bad_{self.unique}@example.com", "provider": "yahoo"}, timeout=15)
        assert r.status_code == 400

    def test_zzz_delete(self, auth_headers):
        for aid in (TestAssignments.ol_id, TestAssignments.gm_id):
            r = requests.delete(f"{BASE_URL}/api/assignments/{aid}", headers=auth_headers, timeout=15)
            assert r.status_code == 200
        # verify gone
        r = requests.get(f"{BASE_URL}/api/assignments", headers=auth_headers, timeout=15)
        ids = {a["id"] for a in r.json()}
        assert TestAssignments.ol_id not in ids
        assert TestAssignments.gm_id not in ids


# ---------- Mailboxes / OAuth ----------
class TestMailboxes:
    def test_connect_not_configured(self, auth_headers):
        # create fresh assignment
        email = f"TEST_conn_{uuid.uuid4().hex[:6]}@example.com"
        c = requests.post(f"{BASE_URL}/api/assignments", headers=auth_headers,
                         json={"email": email, "provider": "outlook_graph"}, timeout=15)
        assert c.status_code == 200
        aid = c.json()["id"]
        try:
            r = requests.get(f"{BASE_URL}/api/mailboxes/connect", headers=auth_headers,
                             params={"email_norm": email.lower()}, timeout=15)
            assert r.status_code == 400
            assert "not configured" in r.json().get("detail", "").lower()
        finally:
            requests.delete(f"{BASE_URL}/api/assignments/{aid}", headers=auth_headers, timeout=15)

    def test_oauth_callback_invalid_state(self):
        # do not follow redirects, so we can inspect Location
        r = requests.get(f"{BASE_URL}/api/oauth/microsoft/callback",
                         params={"state": "not-a-real-state", "code": "xxx"},
                         allow_redirects=False, timeout=15)
        assert r.status_code in (302, 307)
        loc = r.headers.get("location", "")
        assert "error=invalid_state" in loc

    def test_oauth_callback_missing_state(self):
        r = requests.get(f"{BASE_URL}/api/oauth/microsoft/callback",
                         allow_redirects=False, timeout=15)
        assert r.status_code in (302, 307)
        assert "error=missing_state" in r.headers.get("location", "")


# ---------- Search ----------
class TestSearch:
    def test_search_outlook_not_connected(self, auth_headers):
        email = f"TEST_srch_ol_{uuid.uuid4().hex[:6]}@example.com"
        c = requests.post(f"{BASE_URL}/api/assignments", headers=auth_headers,
                         json={"email": email, "provider": "outlook_graph"}, timeout=15)
        aid = c.json()["id"]
        try:
            r = requests.post(f"{BASE_URL}/api/search", headers=auth_headers,
                              json={"email_norm": email.lower(), "category": "login_code"}, timeout=20)
            assert r.status_code == 200
            d = r.json()
            assert d["found"] is False
            assert d["reason"] == "not_connected"
        finally:
            requests.delete(f"{BASE_URL}/api/assignments/{aid}", headers=auth_headers, timeout=15)

    def test_search_gmail_not_configured(self, auth_headers):
        email = f"TEST_srch_gm_{uuid.uuid4().hex[:6]}@example.com"
        c = requests.post(f"{BASE_URL}/api/assignments", headers=auth_headers,
                         json={"email": email, "provider": "gmail_imap"}, timeout=15)
        aid = c.json()["id"]
        try:
            r = requests.post(f"{BASE_URL}/api/search", headers=auth_headers,
                              json={"email_norm": email.lower(), "category": "login_code"}, timeout=20)
            assert r.status_code == 200
            d = r.json()
            assert d["found"] is False
            assert d["reason"] == "not_configured"
        finally:
            requests.delete(f"{BASE_URL}/api/assignments/{aid}", headers=auth_headers, timeout=15)

    def test_search_unknown_category(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/search", headers=auth_headers,
                          json={"email_norm": "x@y.com", "category": "nope"}, timeout=15)
        assert r.status_code == 400

    def test_search_no_assignment(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/search", headers=auth_headers,
                          json={"email_norm": "nonexistent_TEST@nope.com", "category": "login_code"}, timeout=15)
        assert r.status_code == 404
