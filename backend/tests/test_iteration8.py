"""Iteration 8 — verify real Resend delivery to arbitrary recipient
after eghanavisa.com domain verification + SENDER_EMAIL=noreply@eghanavisa.com.

Also regression: /api/config, admin auth for email test endpoint.

To limit spam, this file makes at most 3 REAL Resend sends total:
  1) test_real_send_to_arbitrary_recipient (submitted / en)
  2) test_e2e_submitted_email_via_payment (submitted via E2E)
  3) test_e2e_admin_status_transitions (in_progress + done -> 2 sends)
Total worst-case = 4 real sends but focused on 1 gmail recipient.
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
ARBITRARY_EMAIL = "liportalmerchand@gmail.com"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/admin/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.status_code} {r.text}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- Config regression ----------
class TestConfigRegression:
    def test_config_ok_after_env_change(self):
        r = requests.get(f"{BASE_URL}/api/config", timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "visa_types" in data
        assert isinstance(data["visa_types"], list)
        assert len(data["visa_types"]) >= 1


# ---------- Auth ----------
class TestEmailEndpointAuth:
    def test_no_token(self):
        r = requests.post(
            f"{BASE_URL}/api/admin/email/test",
            json={"recipient": ARBITRARY_EMAIL, "template_name": "submitted", "lang": "en"},
            timeout=10,
        )
        assert r.status_code in (401, 403)

    def test_invalid_token(self):
        r = requests.post(
            f"{BASE_URL}/api/admin/email/test",
            headers={"Authorization": "Bearer invalid.jwt.token"},
            json={"recipient": ARBITRARY_EMAIL, "template_name": "submitted", "lang": "en"},
            timeout=10,
        )
        assert r.status_code in (401, 403)


# ---------- Real Resend to arbitrary recipient ----------
class TestRealResendArbitraryRecipient:
    """Domain verified -> Resend accepts any recipient."""

    def test_real_send_to_arbitrary_recipient(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/admin/email/test",
            headers=admin_headers,
            json={"recipient": ARBITRARY_EMAIL, "template_name": "submitted", "lang": "en"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True, data
        # Post-verification: MUST be real delivery.
        assert data.get("simulated") is False, f"expected real delivery, got {data}"
        rid = data.get("resend_id")
        assert rid, f"expected non-empty resend_id got {data}"
        assert re.match(r"[0-9a-f-]{30,}", rid.lower()), rid
        assert data.get("error") in (None, "")

        # Verify email_log entry matches
        log = requests.get(
            f"{BASE_URL}/api/admin/email-log", headers=admin_headers, timeout=15
        ).json()
        matching = [e for e in log if e.get("resend_id") == rid]
        assert matching, "email_log missing entry for the just-sent email"
        entry = matching[0]
        assert entry["simulated"] is False
        assert entry["recipient"] == ARBITRARY_EMAIL


# ---------- Full E2E ----------
class TestE2ESubmittedEmail:
    def test_e2e_submitted_email_via_payment(self, admin_headers):
        cfg = requests.get(f"{BASE_URL}/api/config", timeout=10).json()
        visa = next((v for v in cfg["visa_types"] if v.get("active", True)), None)
        assert visa, "no active visa type"

        payload = {
            "visa_code": visa["code"],
            "passport_country": "United States",
            "passport_number": "P" + str(int(time.time()))[-7:],
            "passport_type": "Ordinary",
            "passport_expiry": "2030-01-01",
            "travelling_from": "United States",
            "arrival_date": "2026-06-01",
            "departure_date": "2026-06-15",
            "full_name": "TEST Iteration8 E2E",
            "email": ARBITRARY_EMAIL,
            "phone": "+233000000000",
            "profession": "Engineer",
            "processing": "regular",
            "lang": "en",
        }
        r = requests.post(f"{BASE_URL}/api/applications", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        tracking = r.json()["tracking_no"]

        r = requests.post(
            f"{BASE_URL}/api/payments/confirm",
            json={"tracking_no": tracking, "success": True},
            timeout=20,
        )
        assert r.status_code == 200, r.text

        time.sleep(1.5)
        log = requests.get(
            f"{BASE_URL}/api/admin/email-log", headers=admin_headers, timeout=15
        ).json()
        # Match on tracking to be safe
        submitted = [
            e for e in log
            if e["template_name"] == "submitted"
            and e["recipient"] == ARBITRARY_EMAIL
            and tracking in ((e.get("html") or "") + (e.get("subject") or ""))
        ]
        assert submitted, f"no submitted email logged for {tracking}"
        latest = submitted[0]
        assert latest.get("simulated") is False, f"expected real delivery, got {latest}"
        assert latest.get("resend_id"), f"expected resend_id, got {latest}"

        pytest.tracking_it8 = tracking

    def test_e2e_admin_status_transitions(self, admin_headers):
        tracking = getattr(pytest, "tracking_it8", None)
        if not tracking:
            pytest.skip("previous e2e step did not create a tracking")

        for status in ("in_progress", "done"):
            r = requests.post(
                f"{BASE_URL}/api/admin/applications/{tracking}/status",
                headers=admin_headers,
                json={"status": status},
                timeout=20,
            )
            assert r.status_code == 200, r.text

        time.sleep(1.5)
        log = requests.get(
            f"{BASE_URL}/api/admin/email-log", headers=admin_headers, timeout=15
        ).json()
        ips = [
            e for e in log
            if e["template_name"] == "in_progress"
            and e["recipient"] == ARBITRARY_EMAIL
            and tracking in ((e.get("html") or "") + (e.get("subject") or ""))
        ]
        dones = [
            e for e in log
            if e["template_name"] == "done"
            and e["recipient"] == ARBITRARY_EMAIL
            and tracking in ((e.get("html") or "") + (e.get("subject") or ""))
        ]
        assert ips, "no in_progress email logged"
        assert dones, "no done email logged"
        # Both should be REAL delivery post-verification
        assert ips[0].get("simulated") is False, f"in_progress not real: {ips[0]}"
        assert dones[0].get("simulated") is False, f"done not real: {dones[0]}"
        assert ips[0].get("resend_id"), "in_progress missing resend_id"
        assert dones[0].get("resend_id"), "done missing resend_id"
