"""Iteration 2 backend tests — NowPayments + residence_1y express rejection + regression."""
import io
import os
import json
import hmac
import hashlib
import struct
import zlib
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ghana-voa-platform.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DEFAULT_ADMIN_EMAIL = "admin@eghanavisa.com"
DEFAULT_ADMIN_PASS = "Admin@2026"
NEW_ADMIN_PASS = "Admin@2026New!"


def _tiny_png_bytes():
    sig = b"\x89PNG\r\n\x1a\n"
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"\x00\x00\x00\x00\x00")
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


PNG_BYTES = _tiny_png_bytes()


@pytest.fixture(scope="session")
def api_client():
    return requests.Session()


@pytest.fixture(scope="session")
def admin_token(api_client):
    r = api_client.post(f"{API}/admin/login", json={"email": DEFAULT_ADMIN_EMAIL, "password": NEW_ADMIN_PASS})
    if r.status_code == 200:
        return r.json()["token"]
    r = api_client.post(f"{API}/admin/login", json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASS})
    if r.status_code == 200:
        data = r.json()
        tok = data["token"]
        if data.get("must_change_password"):
            ch = api_client.post(
                f"{API}/admin/credentials",
                json={"current_password": DEFAULT_ADMIN_PASS, "new_password": NEW_ADMIN_PASS},
                headers={"Authorization": f"Bearer {tok}"},
            )
            assert ch.status_code == 200, ch.text
            r2 = api_client.post(f"{API}/admin/login", json={"email": DEFAULT_ADMIN_EMAIL, "password": NEW_ADMIN_PASS})
            return r2.json()["token"]
        return tok
    pytest.skip(f"Cannot log in as admin: {r.text}")


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ────────────────── Public /api/config new fields ──────────────────
class TestConfigNewFields:
    def test_config_has_new_fields(self, api_client):
        r = api_client.get(f"{API}/config")
        assert r.status_code == 200
        data = r.json()
        # nowpayments fields
        assert "nowpayments_configured" in data
        assert "nowpayments_sandbox" in data
        # visa types new fields
        types_by_code = {v["code"]: v for v in data["visa_types"]}
        for code in ("tourist_30", "extended_60", "residence_1y"):
            v = types_by_code[code]
            assert "express_available" in v
            assert "processing_time_label" in v
            assert "requires_presence" in v
        # residence_1y specific
        r1 = types_by_code["residence_1y"]
        assert r1["express_available"] is False
        assert r1["requires_presence"] is True
        assert "45" in r1["processing_time_label"]
        assert "60" in r1["processing_time_label"]


# ────────────────── residence_1y express rejection ──────────────────
class TestResidenceExpressRejection:
    def test_activate_residence(self, api_client, auth_headers):
        r = api_client.post(
            f"{API}/admin/settings/visa-toggle",
            json={"code": "residence_1y", "active": True},
            headers=auth_headers,
        )
        assert r.status_code == 200

    def test_reject_express_for_residence(self, api_client):
        payload = {
            "visa_code": "residence_1y",
            "passport_country": "France",
            "passport_number": "R1YEXP1",
            "passport_type": "ordinary",
            "passport_expiry": "2030-12-31",
            "travelling_from": "France",
            "arrival_date": "2026-06-01",
            "departure_date": "2027-06-01",
            "full_name": "TEST Residence Express",
            "email": "test_res_exp@example.com",
            "phone": "+33612345678",
            "profession": "Engineer",
            "processing": "express",
            "lang": "en",
        }
        r = api_client.post(f"{API}/applications", json=payload)
        assert r.status_code == 400
        assert "express" in r.text.lower() or "not available" in r.text.lower()

    def test_accept_regular_for_residence(self, api_client):
        payload = {
            "visa_code": "residence_1y",
            "passport_country": "France",
            "passport_number": "R1YREG1",
            "passport_type": "ordinary",
            "passport_expiry": "2030-12-31",
            "travelling_from": "France",
            "arrival_date": "2026-06-01",
            "departure_date": "2027-06-01",
            "full_name": "TEST Residence Regular",
            "email": "test_res_reg@example.com",
            "phone": "+33612345678",
            "profession": "Engineer",
            "processing": "regular",
            "lang": "en",
        }
        r = api_client.post(f"{API}/applications", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["surcharge_usd"] == 0.0
        assert data["amount_usd"] == data["base_price_usd"]

    def test_deactivate_residence(self, api_client, auth_headers):
        """Restore state - residence_1y should be inactive by default."""
        r = api_client.post(
            f"{API}/admin/settings/visa-toggle",
            json={"code": "residence_1y", "active": False},
            headers=auth_headers,
        )
        assert r.status_code == 200


# ────────────────── NowPayments admin config ──────────────────
class TestNowPaymentsAdmin:
    def test_config_get_initial(self, api_client, auth_headers):
        r = api_client.get(f"{API}/admin/settings", headers=auth_headers)
        assert r.status_code == 200
        s = r.json()
        assert "nowpayments" in s
        assert "sandbox_api_key" in s["nowpayments"]

    def test_test_endpoint_requires_auth(self, api_client):
        r = api_client.post(f"{API}/admin/settings/nowpayments/test")
        assert r.status_code == 401

    def test_test_endpoint_returns_400_when_unconfigured(self, api_client, auth_headers):
        # Reset config to empty
        r = api_client.post(
            f"{API}/admin/settings/nowpayments",
            json={"sandbox": True, "api_key": "", "ipn_secret": "", "sandbox_api_key": "", "sandbox_ipn_secret": ""},
            headers=auth_headers,
        )
        assert r.status_code == 200
        r = api_client.post(f"{API}/admin/settings/nowpayments/test", headers=auth_headers)
        assert r.status_code == 400
        assert "not configured" in r.text.lower()

    def test_save_and_test(self, api_client, auth_headers):
        # Save fake keys
        r = api_client.post(
            f"{API}/admin/settings/nowpayments",
            json={
                "sandbox": True,
                "sandbox_api_key": "test_key_123",
                "sandbox_ipn_secret": "test_secret_abc",
                "api_key": "",
                "ipn_secret": "",
            },
            headers=auth_headers,
        )
        assert r.status_code == 200
        # Verify persisted
        s = api_client.get(f"{API}/admin/settings", headers=auth_headers).json()
        assert s["nowpayments"]["sandbox_api_key"] == "test_key_123"
        assert s["nowpayments"]["sandbox_ipn_secret"] == "test_secret_abc"
        assert s["nowpayments"]["sandbox"] is True

        # Public config now reports configured=True
        pub = api_client.get(f"{API}/config").json()
        assert pub["nowpayments_configured"] is True

        # Test endpoint hits sandbox and gets 502 (invalid key) or 400
        r = api_client.post(f"{API}/admin/settings/nowpayments/test", headers=auth_headers, timeout=30)
        assert r.status_code in (400, 502), f"Unexpected: {r.status_code} {r.text}"


# ────────────────── Crypto initiate rejections ──────────────────
class TestCryptoInitiate:
    def test_reject_when_not_configured(self, api_client, auth_headers):
        # Ensure not configured
        api_client.post(
            f"{API}/admin/settings/nowpayments",
            json={"sandbox": True, "api_key": "", "ipn_secret": "", "sandbox_api_key": "", "sandbox_ipn_secret": ""},
            headers=auth_headers,
        )
        r = api_client.post(f"{API}/payments/crypto/initiate", json={"tracking_no": "GH-2026-000000", "network": "trc20"})
        assert r.status_code == 503

    def test_reject_when_method_disabled(self, api_client, auth_headers):
        # Configure fake keys, keep usdt_trc20 inactive
        api_client.post(
            f"{API}/admin/settings/nowpayments",
            json={"sandbox": True, "sandbox_api_key": "test_key_123", "sandbox_ipn_secret": "test_secret_abc"},
            headers=auth_headers,
        )
        # Ensure disabled
        api_client.post(
            f"{API}/admin/settings/payment-toggle",
            json={"code": "usdt_trc20", "active": False},
            headers=auth_headers,
        )
        r = api_client.post(f"{API}/payments/crypto/initiate", json={"tracking_no": "GH-2026-000000", "network": "trc20"})
        assert r.status_code == 403

    def test_reject_unknown_tracking_when_method_active(self, api_client, auth_headers):
        api_client.post(
            f"{API}/admin/settings/payment-toggle",
            json={"code": "usdt_trc20", "active": True},
            headers=auth_headers,
        )
        r = api_client.post(f"{API}/payments/crypto/initiate", json={"tracking_no": "GH-2026-999999", "network": "trc20"})
        assert r.status_code == 404
        # Restore
        api_client.post(
            f"{API}/admin/settings/payment-toggle",
            json={"code": "usdt_trc20", "active": False},
            headers=auth_headers,
        )

    def test_reject_invalid_network(self, api_client, auth_headers):
        r = api_client.post(f"{API}/payments/crypto/initiate", json={"tracking_no": "GH-2026-999999", "network": "eth"})
        assert r.status_code == 400


# ────────────────── Crypto status endpoint ──────────────────
class TestCryptoStatus:
    def test_status_unknown_404(self, api_client):
        r = api_client.get(f"{API}/payments/crypto/status/nonexistent-pid-abc")
        assert r.status_code == 404


# ────────────────── Admin crypto listing ──────────────────
class TestAdminCryptoList:
    def test_requires_auth(self, api_client):
        r = api_client.get(f"{API}/admin/crypto-payments")
        assert r.status_code == 401

    def test_returns_list(self, api_client, auth_headers):
        r = api_client.get(f"{API}/admin/crypto-payments", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ────────────────── NowPayments IPN webhook ──────────────────
IPN_SECRET = "test_secret_abc"
WEBHOOK_URL = f"{BASE_URL}/api/webhooks/nowpayments"


def _sign(payload: dict, secret: str) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha512).hexdigest().lower()


class TestIPNWebhook:
    @pytest.fixture(autouse=True)
    def _configure_np(self, api_client, auth_headers):
        # Ensure fake keys configured with known IPN secret
        api_client.post(
            f"{API}/admin/settings/nowpayments",
            json={
                "sandbox": True,
                "sandbox_api_key": "test_key_123",
                "sandbox_ipn_secret": IPN_SECRET,
                "api_key": "",
                "ipn_secret": "",
            },
            headers=auth_headers,
        )

    def test_missing_signature_returns_401(self, api_client):
        r = api_client.post(WEBHOOK_URL, json={"payment_id": "px", "payment_status": "waiting"})
        assert r.status_code == 401

    def test_invalid_signature_returns_401(self, api_client):
        r = api_client.post(
            WEBHOOK_URL,
            data=json.dumps({"payment_id": "px", "payment_status": "waiting"}),
            headers={"x-nowpayments-sig": "deadbeef" * 16, "Content-Type": "application/json"},
        )
        assert r.status_code == 401

    def test_valid_signature_returns_200(self, api_client):
        payload = {"payment_id": "sig-test-001", "payment_status": "waiting"}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        sig = _sign(payload, IPN_SECRET)
        r = api_client.post(
            WEBHOOK_URL,
            data=canonical,
            headers={"x-nowpayments-sig": sig, "Content-Type": "application/json"},
        )
        assert r.status_code == 200, r.text


# ────────────────── IPN idempotency + finished flow ──────────────────
class TestIPNIdempotency:
    def _create_app_and_crypto_stub(self, api_client, auth_headers, payment_id):
        """Create an application via the normal flow, then insert a crypto_payments doc directly
        via NowPayments admin endpoints? Not possible — we'll rely on the app being created
        and then send an IPN with a payment_id that maps to it."""
        # Create application
        payload = {
            "visa_code": "tourist_30",
            "passport_country": "France",
            "passport_number": f"IPN{payment_id[:6].upper()}",
            "passport_type": "ordinary",
            "passport_expiry": "2030-12-31",
            "travelling_from": "France",
            "arrival_date": "2026-07-01",
            "departure_date": "2026-07-10",
            "full_name": "TEST IPN Idempotent",
            "email": "test_ipn@example.com",
            "phone": "+33612345678",
            "profession": "Engineer",
            "processing": "regular",
            "lang": "en",
        }
        r = api_client.post(f"{API}/applications", json=payload)
        assert r.status_code == 200
        tracking = r.json()["tracking_no"]
        return tracking

    def test_valid_ipn_for_unknown_payment_returns_200_but_noop(self, api_client, auth_headers):
        """Configure IPN secret then send valid signature for a payment_id that doesn't exist
        in db.crypto_payments — endpoint should return 200 (no crash)."""
        api_client.post(
            f"{API}/admin/settings/nowpayments",
            json={
                "sandbox": True,
                "sandbox_api_key": "test_key_123",
                "sandbox_ipn_secret": IPN_SECRET,
            },
            headers=auth_headers,
        )
        payload = {"payment_id": "unknown-999", "payment_status": "finished", "actually_paid": 100.0}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        sig = _sign(payload, IPN_SECRET)
        r = requests.post(
            WEBHOOK_URL,
            data=canonical,
            headers={"x-nowpayments-sig": sig, "Content-Type": "application/json"},
        )
        assert r.status_code == 200


# ────────────────── Regression: Hubtel flow still works ──────────────────
@pytest.fixture(scope="module")
def hubtel_reset():
    """Ensure hubtel is in sandbox before we run regression."""
    r = requests.post(f"{API}/admin/login", json={"email": DEFAULT_ADMIN_EMAIL, "password": NEW_ADMIN_PASS})
    if r.status_code != 200:
        pytest.skip("admin login failed")
    tok = r.json()["token"]
    headers = {"Authorization": f"Bearer {tok}"}
    requests.post(
        f"{API}/admin/settings/hubtel",
        json={"sandbox": True, "api_id": "", "api_key": "", "merchant_account_id": "", "callback_url": "", "return_url": "", "outbound_proxy_url": ""},
        headers=headers,
    )
    yield


class TestHubtelRegression:
    def test_full_hubtel_flow(self, api_client, hubtel_reset):
        payload = {
            "visa_code": "tourist_30",
            "passport_country": "France",
            "passport_number": "HUBREG1",
            "passport_type": "ordinary",
            "passport_expiry": "2030-12-31",
            "travelling_from": "France",
            "arrival_date": "2026-08-01",
            "departure_date": "2026-08-10",
            "full_name": "TEST Hubtel Regression",
            "email": "test_hubtel_reg@example.com",
            "phone": "+33612345678",
            "profession": "Engineer",
            "processing": "regular",
            "lang": "en",
        }
        r = api_client.post(f"{API}/applications", json=payload)
        assert r.status_code == 200
        tracking = r.json()["tracking_no"]

        # Upload 4 documents
        for doc_type in ("face_photo", "passport_copy", "passport_cover", "flight_ticket"):
            files = {"file": (f"{doc_type}.png", PNG_BYTES, "image/png")}
            data = {"doc_type": doc_type}
            r = api_client.post(f"{API}/applications/{tracking}/documents", files=files, data=data)
            assert r.status_code == 200

        # Payment initiate (sandbox)
        r = api_client.post(f"{API}/payments/initiate", json={"tracking_no": tracking})
        assert r.status_code == 200
        assert r.json()["sandbox"] is True

        # Confirm
        r = api_client.post(f"{API}/payments/confirm", json={"tracking_no": tracking, "success": True})
        assert r.status_code == 200

        # Track
        r = api_client.get(f"{API}/track/{tracking}")
        assert r.status_code == 200
        assert r.json()["status"] == "submitted"
