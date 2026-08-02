"""Iteration 11 backend tests — Hubtel DB creds, currency payload, security,
outbound_proxy backward-compat, NowPayments preview validation, admin
regression endpoints."""
import os
import re
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ghana-visa-app.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@eghanavisa.com"
ADMIN_PASS = "Admin@2026"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(api):
    r = api.post(f"{BASE_URL}/api/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_api(api, admin_token):
    api.headers.update({"Authorization": f"Bearer {admin_token}"})
    return api


# ────────── Task 1: Save Hubtel creds and verify GET returns them ──────────
class TestHubtelCreds:
    def test_save_hubtel_creds_from_review_request(self, admin_api):
        """Save the Hubtel creds requested by the user (empty api_key on purpose)."""
        payload = {
            "sandbox": False,
            "api_id": "g28qL0D",
            "api_key": "",                    # intentionally empty
            "merchant_account_id": "2024252",
            "callback_url": "",
            "return_url": "",
            "outbound_proxy_url": "",         # backward compat, may be omitted
        }
        r = admin_api.post(f"{BASE_URL}/api/admin/settings/hubtel", json=payload)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    def test_get_settings_returns_saved_hubtel(self, admin_api):
        r = admin_api.get(f"{BASE_URL}/api/admin/settings")
        assert r.status_code == 200
        h = r.json().get("hubtel", {})
        assert h.get("api_id") == "g28qL0D", f"api_id mismatch: {h.get('api_id')}"
        assert h.get("merchant_account_id") == "2024252"
        assert h.get("api_key") == ""
        assert h.get("sandbox") is False

    def test_outbound_proxy_backward_compat(self, admin_api):
        """Backend should still accept the old-shape payload including outbound_proxy_url."""
        payload = {
            "sandbox": False,
            "api_id": "g28qL0D",
            "api_key": "",
            "merchant_account_id": "2024252",
            "callback_url": "",
            "return_url": "",
            "outbound_proxy_url": "http://old.proxy.example:8080",
        }
        r = admin_api.post(f"{BASE_URL}/api/admin/settings/hubtel", json=payload)
        assert r.status_code == 200, r.text

        # Re-fetch and confirm nothing crashed; api_id/mid still correct
        r = admin_api.get(f"{BASE_URL}/api/admin/settings")
        h = r.json()["hubtel"]
        assert h["api_id"] == "g28qL0D"
        assert h["merchant_account_id"] == "2024252"

        # Reset proxy back to empty (cleanup)
        payload["outbound_proxy_url"] = ""
        r = admin_api.post(f"{BASE_URL}/api/admin/settings/hubtel", json=payload)
        assert r.status_code == 200


# ────────── Task 2: Hubtel payload currency ──────────
class TestHubtelCurrency:
    def test_hubtel_service_payload_has_currency_usd(self):
        """Direct source read — payload must include currency='USD'."""
        with open("/app/backend/hubtel_service.py") as f:
            src = f.read()
        assert re.search(r'"currency"\s*:\s*\(config\.get\("currency"\)\s*or\s*"USD"\)\.upper\(\)', src), \
            "hubtel_service.py must set payload['currency'] = (config.get('currency') or 'USD').upper()"


# ────────── Task 3: Security — no api_key leakage ──────────
class TestHubtelSecurity:
    def test_public_config_never_exposes_api_key(self, api):
        r = api.get(f"{BASE_URL}/api/config")
        assert r.status_code == 200
        text = r.text
        assert "api_key" not in text
        assert "g28qL0D" not in text  # api_id also should not leak in public
        assert "2024252" not in text  # merchant id also should not leak

    def test_admin_settings_requires_auth(self, api):
        # Ensure no Authorization header
        session = requests.Session()
        r = session.get(f"{BASE_URL}/api/admin/settings")
        assert r.status_code in (401, 403), f"unauth access got {r.status_code}"

    def test_admin_settings_only_returns_api_key_to_admin(self, admin_api):
        r = admin_api.get(f"{BASE_URL}/api/admin/settings")
        assert r.status_code == 200
        assert "api_key" in r.json().get("hubtel", {}), "admin must see the api_key field (even if empty)"


# ────────── Task 4: No hardcoded creds in source ──────────
class TestNoHardcodedCredentialsInSource:
    FORBIDDEN = ["g28qL0D", "ES4K8FT", "2024252", "U0VXWjaQ", "re_emKN4"]

    def test_no_hardcoded_credentials_in_backend_py(self):
        """Sweep all backend/*.py — none may contain payment provider creds."""
        import glob
        offenders = []
        for path in glob.glob("/app/backend/**/*.py", recursive=True):
            # tests can contain the id-shaped literals (like 'g28qL0D') for
            # documentation, but skip our own test files
            if "/tests/" in path:
                continue
            with open(path) as f:
                content = f.read()
            for token in self.FORBIDDEN:
                if token in content:
                    offenders.append(f"{path}: contains {token!r}")
        assert not offenders, "Hardcoded creds found:\n" + "\n".join(offenders)


# ────────── Task 5: NowPayments preview validation ──────────
class TestNowPaymentsPreview:
    def test_np_test_endpoint_ok_production(self, admin_api):
        r = admin_api.post(f"{BASE_URL}/api/admin/settings/nowpayments/test", json={})
        # accept 200 with mode:production OR skip if creds unset in preview DB
        if r.status_code == 400 and "not configured" in r.text.lower():
            pytest.skip("NowPayments creds not saved in preview DB — mode logic verified by unit test")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("mode") == "production", f"expected production, got {d.get('mode')}"


# ────────── Task 6: Regression — E2E application + Hubtel sandbox ──────────
class TestApplicationRegression:
    tracking_no = None

    def test_create_tourist_evisa(self, api):
        payload = {
            "visa_code": "tourist_evisa",
            "passport_country": "United States",
            "passport_number": f"TEST{uuid.uuid4().hex[:8].upper()}",
            "passport_type": "Ordinary",
            "passport_expiry": "2030-12-31",
            "travelling_from": "United States",
            "arrival_date": "2026-06-01",
            "departure_date": "2026-06-15",
            "full_name": "TEST Iteration11",
            "email": "test_iter11@example.com",
            "phone": "+11234567890",
            "profession": "Engineer",
            "processing": "regular",
        }
        r = api.post(f"{BASE_URL}/api/applications", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "tracking_no" in d
        TestApplicationRegression.tracking_no = d["tracking_no"]

    def test_hubtel_sandbox_fallback(self, api):
        """Since api_key is empty, initiate must fall back to sandbox."""
        assert TestApplicationRegression.tracking_no, "prev test failed"
        r = api.post(
            f"{BASE_URL}/api/payments/initiate",
            json={"tracking_no": TestApplicationRegression.tracking_no},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("sandbox") is True, f"expected sandbox=true (empty api_key), got: {d}"
        assert "checkout_url" in d

    def test_track_application(self, api):
        assert TestApplicationRegression.tracking_no
        # /track only returns 200 for PAID apps. Confirm payment first.
        cr = api.post(
            f"{BASE_URL}/api/payments/confirm",
            json={"tracking_no": TestApplicationRegression.tracking_no, "success": True},
        )
        assert cr.status_code == 200, cr.text
        r = api.get(f"{BASE_URL}/api/track/{TestApplicationRegression.tracking_no}")
        assert r.status_code == 200
        d = r.json()
        assert d["tracking_no"] == TestApplicationRegression.tracking_no


# ────────── Task 7: Admin regression — all endpoints still return 200 ──────────
class TestAdminRegression:
    def test_admin_kpis(self, admin_api):
        r = admin_api.get(f"{BASE_URL}/api/admin/kpis")
        assert r.status_code == 200
        d = r.json()
        assert "total" in d and "submitted" in d

    def test_admin_applications(self, admin_api):
        r = admin_api.get(f"{BASE_URL}/api/admin/applications")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_visa_price(self, admin_api):
        r = admin_api.post(
            f"{BASE_URL}/api/admin/settings/visa-price",
            json={"code": "tourist_evisa", "price_usd": 350},
        )
        assert r.status_code == 200

    def test_admin_express_surcharge(self, admin_api):
        r = admin_api.post(
            f"{BASE_URL}/api/admin/settings/express-surcharge",
            json={"price_usd": 50},
        )
        assert r.status_code == 200

    def test_admin_payment_toggle(self, admin_api):
        r = admin_api.post(
            f"{BASE_URL}/api/admin/settings/payment-toggle",
            json={"code": "hubtel", "active": True},
        )
        assert r.status_code == 200

    def test_admin_usdt_discount(self, admin_api):
        r = admin_api.post(
            f"{BASE_URL}/api/admin/settings/usdt-discount",
            json={"pct": 10},
        )
        assert r.status_code == 200

    def test_admin_whatsapp(self, admin_api):
        r = admin_api.post(
            f"{BASE_URL}/api/admin/settings/whatsapp",
            json={"whatsapp_admin": "+233000000000"},
        )
        assert r.status_code == 200

    def test_admin_ai_model(self, admin_api):
        r = admin_api.post(
            f"{BASE_URL}/api/admin/settings/ai-model",
            json={"ai_model": "gpt-4o-mini"},
        )
        assert r.status_code == 200

    def test_admin_upload_limit(self, admin_api):
        r = admin_api.post(
            f"{BASE_URL}/api/admin/settings/upload-limit",
            json={"max_upload_mb": 8},
        )
        assert r.status_code == 200

    def test_admin_email_templates(self, admin_api):
        r = admin_api.get(f"{BASE_URL}/api/admin/email-templates")
        assert r.status_code == 200

    def test_admin_email_log(self, admin_api):
        r = admin_api.get(f"{BASE_URL}/api/admin/email-log")
        assert r.status_code == 200
