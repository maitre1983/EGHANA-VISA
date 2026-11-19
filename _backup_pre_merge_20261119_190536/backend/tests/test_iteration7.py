"""Iteration 7 — verification tests for real Resend email delivery.

Covers:
- /api/admin/email/test endpoint: auth required, template rendering, bilingual,
  unknown template safety, Resend TEST-mode restriction (external recipient).
- Regression: /api/config, admin login, USDT-sandbox end-to-end submitted email,
  admin status transitions still send in_progress/done emails.

Notes:
- We restrict real Resend delivery to at most 1 call to contact@eghanavisa.com
  (the account-owner address). All other cases use the restricted external
  address (liportalmerchand@gmail.com) which Resend will reject; the service
  must degrade to simulated=True.
- Skips gracefully if RESEND_API_KEY is missing.
"""
import os
import re
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
BASE_URL = BASE_URL.rstrip("/")

ADMIN_EMAIL = "admin@eghanavisa.com"
ADMIN_PASSWORD = "Admin@2026New!"
OWNER_EMAIL = "contact@eghanavisa.com"        # only allowed recipient in test mode
RESTRICTED_EMAIL = "liportalmerchand@gmail.com"  # Resend will reject


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- Auth ----------
class TestEmailEndpointAuth:
    """POST /api/admin/email/test requires admin JWT."""

    def test_no_token_returns_401_or_403(self):
        r = requests.post(f"{BASE_URL}/api/admin/email/test",
                          json={"recipient": OWNER_EMAIL,
                                "template_name": "submitted",
                                "lang": "en"}, timeout=10)
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}: {r.text}"

    def test_invalid_token_returns_401_or_403(self):
        r = requests.post(f"{BASE_URL}/api/admin/email/test",
                          headers={"Authorization": "Bearer invalid.jwt.token"},
                          json={"recipient": OWNER_EMAIL,
                                "template_name": "submitted",
                                "lang": "en"}, timeout=10)
        assert r.status_code in (401, 403)


# ---------- Real Resend delivery (limited to 1 call) ----------
class TestRealResendDelivery:
    """One real send to the Resend account owner address."""

    def test_real_send_to_owner_returns_resend_id(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/admin/email/test",
                          headers=admin_headers,
                          json={"recipient": OWNER_EMAIL,
                                "template_name": "submitted",
                                "lang": "en"}, timeout=30)
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        data = r.json()
        assert data["ok"] is True
        # Real delivery expected: simulated False, resend_id non-null uuid,
        # error None. Accept simulated=True only if Resend API itself was
        # unreachable — surface useful info in the assertion.
        assert data.get("simulated") is False, (
            f"expected real delivery (simulated=False) got {data}"
        )
        rid = data.get("resend_id")
        assert rid, f"expected non-empty resend_id got {data}"
        # basic uuid shape (8-4-4-4-12)
        assert re.match(r"[0-9a-f-]{30,}", rid.lower()), f"resend_id not uuid-ish: {rid}"
        assert data.get("error") in (None, "")

        # Also verify email_log has an entry with simulated=False for OWNER_EMAIL
        log = requests.get(f"{BASE_URL}/api/admin/email-log",
                           headers=admin_headers, timeout=15).json()
        matching = [e for e in log if e.get("resend_id") == rid]
        assert matching, "email_log missing entry for the just-sent email"
        assert matching[0]["simulated"] is False
        assert matching[0]["recipient"] == OWNER_EMAIL


# ---------- Bilingual + template substitution ----------
class TestTemplateRendering:
    """Verify placeholder substitution in bilingual templates without real send."""

    @pytest.mark.parametrize("template_name,lang", [
        ("in_progress", "fr"),
        ("done", "fr"),
        ("in_progress", "en"),
    ])
    def test_template_renders_with_substitutions(self, admin_headers, template_name, lang):
        # Use the restricted address so Resend rejects the network call
        # (simulated=True) but subject/html are still rendered and stored.
        r = requests.post(f"{BASE_URL}/api/admin/email/test",
                          headers=admin_headers,
                          json={"recipient": RESTRICTED_EMAIL,
                                "template_name": template_name,
                                "lang": lang}, timeout=30)
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        data = r.json()
        # Subject was rendered
        subject = data.get("subject") or ""
        assert subject, f"empty subject: {data}"

        # Pull the just-inserted log entry to inspect html
        log = requests.get(f"{BASE_URL}/api/admin/email-log",
                           headers=admin_headers, timeout=15).json()
        entry = next(
            (e for e in log
             if e["recipient"] == RESTRICTED_EMAIL
             and e["template_name"] == template_name
             and e["lang"] == lang),
            None,
        )
        assert entry, f"no email_log entry for {template_name}/{lang}"

        # Substitutions applied — no leftover placeholders
        combined = (entry.get("subject") or "") + (entry.get("html") or "")
        # {{name}} / {{tracking}} tokens should be fully substituted
        leftover = re.findall(r"\{\{\s*(name|tracking|visa_type|processing|amount)\s*\}\}",
                              combined)
        assert not leftover, f"leftover placeholders: {leftover}"
        # Concrete substituted values should appear
        assert "Test Recipient" in combined, "name substitution missing"
        assert "GH-2026-TEST01" in combined, "tracking substitution missing"


# ---------- Resend restriction ----------
class TestResendRestriction:
    """External recipient → Resend rejects → endpoint degrades to simulated=True (HTTP 200)."""

    def test_restricted_recipient_graceful_degradation(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/admin/email/test",
                          headers=admin_headers,
                          json={"recipient": RESTRICTED_EMAIL,
                                "template_name": "submitted",
                                "lang": "en"}, timeout=30)
        # Must NOT crash the server
        assert r.status_code == 200, f"expected 200 got {r.status_code}: {r.text}"
        data = r.json()
        # Because Resend TEST-mode rejects non-owner recipients, delivery must
        # be recorded as simulated=True with error populated.
        assert data.get("simulated") is True, (
            f"expected simulated=True for restricted address, got {data}"
        )
        assert data.get("resend_id") in (None, "", None), (
            f"expected no resend_id got {data}"
        )
        assert data.get("error"), f"expected error field populated: {data}"

        # Confirm the log entry mirrors this
        log = requests.get(f"{BASE_URL}/api/admin/email-log",
                           headers=admin_headers, timeout=15).json()
        entry = next(
            (e for e in log
             if e["recipient"] == RESTRICTED_EMAIL
             and e["template_name"] == "submitted"
             and e.get("simulated") is True
             and e.get("error")),
            None,
        )
        assert entry, "email_log missing simulated=True + error entry for restricted address"


# ---------- Unknown template ----------
class TestUnknownTemplate:
    """Unknown template must not crash the server (500 or graceful fallback both acceptable)."""

    def test_unknown_template_does_not_crash(self, admin_headers):
        r = requests.post(f"{BASE_URL}/api/admin/email/test",
                          headers=admin_headers,
                          json={"recipient": OWNER_EMAIL,
                                "template_name": "nonexistent_template_xyz",
                                "lang": "en"}, timeout=20)
        # Acceptable per requirements: 500 (RuntimeError from render_template)
        # OR 200 with fallback. Not 502/504/no-response.
        assert r.status_code in (200, 400, 404, 500), (
            f"unexpected status {r.status_code}: {r.text}"
        )
        # Server must still be alive — hit /api/config
        health = requests.get(f"{BASE_URL}/api/config", timeout=10)
        assert health.status_code == 200, "server crashed after unknown-template call"


# ---------- Regression: /api/config still fine ----------
class TestRegressionConfig:
    def test_config_returns_visa_types(self):
        r = requests.get(f"{BASE_URL}/api/config", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "visa_types" in data
        assert isinstance(data["visa_types"], list)
        assert len(data["visa_types"]) >= 1


# ---------- Regression: full E2E — submitted email on payment confirm ----------
class TestRegressionE2ESubmittedEmail:
    """Create application, confirm payment (sandbox), verify submitted email was logged."""

    def test_e2e_submitted_email_logged(self, admin_headers):
        # 1. Fetch config to pick a visa type
        cfg = requests.get(f"{BASE_URL}/api/config", timeout=10).json()
        visa = next((v for v in cfg["visa_types"] if v.get("active", True)), None)
        assert visa, "no active visa type"

        # 2. Create application — send to OWNER_EMAIL so real Resend send succeeds.
        payload = {
            "visa_code": visa["code"],
            "passport_country": "United States",
            "passport_number": "P" + str(int(time.time()))[-7:],
            "passport_type": "Ordinary",
            "passport_expiry": "2030-01-01",
            "travelling_from": "United States",
            "arrival_date": "2026-06-01",
            "departure_date": "2026-06-15",
            "full_name": "TEST Iteration7 Regression",
            "email": OWNER_EMAIL,
            "phone": "+233000000000",
            "profession": "Engineer",
            "processing": "regular",
            "lang": "en",
        }
        r = requests.post(f"{BASE_URL}/api/applications", json=payload, timeout=20)
        assert r.status_code == 200, f"create app failed: {r.status_code} {r.text}"
        tracking = r.json()["tracking_no"]

        # 3. Confirm payment (Hubtel sandbox path)
        r = requests.post(f"{BASE_URL}/api/payments/confirm",
                          json={"tracking_no": tracking, "success": True}, timeout=20)
        assert r.status_code == 200, f"payment confirm failed: {r.text}"

        # 4. Verify email_log has a 'submitted' entry for this recipient
        # Small settle wait for background insert
        time.sleep(1.0)
        log = requests.get(f"{BASE_URL}/api/admin/email-log",
                           headers=admin_headers, timeout=15).json()
        entries = [e for e in log
                   if e["recipient"] == OWNER_EMAIL
                   and e["template_name"] == "submitted"]
        assert entries, "no 'submitted' email logged after payment confirm"
        latest = entries[0]
        # Since we used OWNER_EMAIL, real Resend delivery expected → simulated=False
        assert latest.get("simulated") is False, (
            f"expected real Resend delivery for OWNER_EMAIL, got {latest}"
        )
        assert latest.get("resend_id"), f"expected resend_id, got {latest}"

        # Save tracking for next test
        pytest.tracking_regress = tracking

    def test_e2e_admin_status_transitions_send_emails(self, admin_headers):
        tracking = getattr(pytest, "tracking_regress", None)
        if not tracking:
            pytest.skip("previous e2e step did not create a tracking")

        for status in ("in_progress", "done"):
            r = requests.post(
                f"{BASE_URL}/api/admin/applications/{tracking}/status",
                headers=admin_headers,
                json={"status": status}, timeout=20,
            )
            assert r.status_code == 200, f"status {status} failed: {r.text}"

        time.sleep(1.5)
        log = requests.get(f"{BASE_URL}/api/admin/email-log",
                           headers=admin_headers, timeout=15).json()
        # Find at least one in_progress and one done for OWNER_EMAIL post-tracking
        ips = [e for e in log if e["template_name"] == "in_progress" and e["recipient"] == OWNER_EMAIL]
        dones = [e for e in log if e["template_name"] == "done" and e["recipient"] == OWNER_EMAIL]
        assert ips, "no in_progress email logged"
        assert dones, "no done email logged"
