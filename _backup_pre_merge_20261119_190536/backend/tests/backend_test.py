"""End-to-end backend tests for e.GHANA Visa Portal."""
import io
import os
import time
import struct
import zlib
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ghana-eta-hub--8jwgo6s2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DEFAULT_ADMIN_EMAIL = "admin@eghanavisa.com"
DEFAULT_ADMIN_PASS = "Admin@2026"
NEW_ADMIN_PASS = "Admin@2026New!"


def _tiny_png_bytes():
    """Generate a valid 1x1 transparent PNG."""
    sig = b"\x89PNG\r\n\x1a\n"
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"\x00\x00\x00\x00\x00")
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


PNG_BYTES = _tiny_png_bytes()


# ────────────────── FIXTURES ──────────────────
@pytest.fixture(scope="session")
def api_client():
    s = requests.Session()
    return s


@pytest.fixture(scope="session")
def admin_token(api_client):
    """Try default password; if wrong, try new; ensure password ends up as NEW."""
    r = api_client.post(f"{API}/admin/login", json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASS})
    if r.status_code == 200:
        data = r.json()
        tok = data["token"]
        # If first login, force change password
        if data.get("must_change_password"):
            ch = api_client.post(
                f"{API}/admin/credentials",
                json={"current_password": DEFAULT_ADMIN_PASS, "new_password": NEW_ADMIN_PASS},
                headers={"Authorization": f"Bearer {tok}"},
            )
            assert ch.status_code == 200, ch.text
            # Re-login with new password
            r2 = api_client.post(f"{API}/admin/login", json={"email": DEFAULT_ADMIN_EMAIL, "password": NEW_ADMIN_PASS})
            assert r2.status_code == 200
            return r2.json()["token"]
        return tok
    # Try new pass (previously rotated)
    r = api_client.post(f"{API}/admin/login", json={"email": DEFAULT_ADMIN_EMAIL, "password": NEW_ADMIN_PASS})
    assert r.status_code == 200, f"Both passwords failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ────────────────── PUBLIC CONFIG ──────────────────
class TestConfig:
    def test_root(self, api_client):
        r = api_client.get(f"{API}/")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_public_config(self, api_client):
        r = api_client.get(f"{API}/config")
        assert r.status_code == 200
        data = r.json()
        assert len(data["visa_types"]) == 3
        assert len(data["payment_methods"]) == 3
        assert data["express_surcharge_usd"] == 50.0
        assert data["hubtel_sandbox"] is True
        assert "max_upload_mb" in data
        assert "whatsapp_admin" in data
        codes = {v["code"] for v in data["visa_types"]}
        assert codes == {"tourist_30", "extended_60", "residence_1y"}

    def test_countries(self, api_client):
        r = api_client.get(f"{API}/countries")
        assert r.status_code == 200
        data = r.json()
        passport = data["passport"]
        travel_from = data["travel_from"]
        # ECOWAS excluded from passport
        for excluded in ("Ghana", "Nigeria", "Senegal", "Togo", "Mali"):
            assert excluded not in passport, f"{excluded} should be excluded from passport"
        # But present in travel_from
        assert "Ghana" in travel_from
        assert "Nigeria" in travel_from
        assert len(passport) < len(travel_from)


# ────────────────── ADMIN AUTH ──────────────────
class TestAdminAuth:
    def test_login_wrong_password(self, api_client):
        r = api_client.post(f"{API}/admin/login", json={"email": DEFAULT_ADMIN_EMAIL, "password": "wrong"})
        assert r.status_code == 401

    def test_login_success(self, admin_token):
        assert admin_token
        assert len(admin_token) > 20

    def test_admin_me(self, api_client, auth_headers):
        r = api_client.get(f"{API}/admin/me", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["email"] == DEFAULT_ADMIN_EMAIL

    def test_admin_endpoints_require_auth(self, api_client):
        endpoints = [
            ("GET", "/admin/kpis"),
            ("GET", "/admin/applications"),
            ("GET", "/admin/settings"),
            ("GET", "/admin/email-templates"),
            ("GET", "/admin/email-log"),
            ("GET", "/admin/me"),
        ]
        for method, path in endpoints:
            r = api_client.request(method, f"{API}{path}")
            assert r.status_code == 401, f"{path} did not require auth: {r.status_code}"

    def test_credentials_bad_current_password(self, api_client, auth_headers):
        r = api_client.post(
            f"{API}/admin/credentials",
            json={"current_password": "wrong", "new_password": "abcdefgh"},
            headers=auth_headers,
        )
        assert r.status_code == 401

    def test_credentials_short_password(self, api_client, auth_headers):
        r = api_client.post(
            f"{API}/admin/credentials",
            json={"current_password": NEW_ADMIN_PASS, "new_password": "short"},
            headers=auth_headers,
        )
        assert r.status_code == 400


# ────────────────── APPLICATION FLOW ──────────────────
@pytest.fixture(scope="module")
def sample_app_payload():
    return {
        "visa_code": "tourist_30",
        "passport_country": "France",
        "passport_number": "TEST12345",
        "passport_type": "ordinary",
        "passport_expiry": "2030-12-31",
        "travelling_from": "France",
        "arrival_date": "2026-06-01",
        "departure_date": "2026-06-15",
        "full_name": "TEST Applicant",
        "email": "test_applicant@example.com",
        "phone": "+33612345678",
        "profession": "Engineer",
        "processing": "express",
        "lang": "en",
    }


class TestApplicationFlow:
    @pytest.fixture(scope="class")
    def tracking(self, api_client, sample_app_payload):
        r = api_client.post(f"{API}/applications", json=sample_app_payload)
        assert r.status_code == 200, r.text
        data = r.json()
        # Validate structure
        assert data["tracking_no"].startswith("GH-2026-") or data["tracking_no"].startswith("GH-2025-")
        assert data["amount_usd"] == 400.0  # 350 + 50 express surcharge
        assert data["surcharge_usd"] == 50.0
        assert data["status"] == "pending_payment"
        assert data["payment_status"] == "pending"
        return data["tracking_no"]

    def test_application_create_bad_visa(self, api_client, sample_app_payload):
        bad = dict(sample_app_payload)
        bad["visa_code"] = "extended_60"  # inactive
        r = api_client.post(f"{API}/applications", json=bad)
        assert r.status_code == 400

    def test_application_create_invalid_processing(self, api_client, sample_app_payload):
        bad = dict(sample_app_payload)
        bad["processing"] = "urgent"
        r = api_client.post(f"{API}/applications", json=bad)
        assert r.status_code == 400

    def test_tracking_before_payment_returns_404(self, api_client, tracking):
        r = api_client.get(f"{API}/track/{tracking}")
        assert r.status_code == 404

    def test_track_unknown(self, api_client):
        r = api_client.get(f"{API}/track/GH-2026-000000")
        assert r.status_code == 404

    def test_upload_documents(self, api_client, tracking):
        for doc_type in ("face_photo", "passport_copy", "passport_cover", "flight_ticket"):
            files = {"file": (f"{doc_type}.png", PNG_BYTES, "image/png")}
            data = {"doc_type": doc_type}
            r = api_client.post(f"{API}/applications/{tracking}/documents", files=files, data=data)
            assert r.status_code == 200, f"Upload {doc_type} failed: {r.status_code} {r.text}"
            j = r.json()
            assert j["ok"] is True
            assert j["doc_type"] == doc_type

    def test_upload_invalid_doc_type(self, api_client, tracking):
        files = {"file": ("x.png", PNG_BYTES, "image/png")}
        data = {"doc_type": "bogus"}
        r = api_client.post(f"{API}/applications/{tracking}/documents", files=files, data=data)
        assert r.status_code == 400

    def test_upload_invalid_extension(self, api_client, tracking):
        files = {"file": ("evil.exe", b"MZ", "application/octet-stream")}
        data = {"doc_type": "face_photo"}
        r = api_client.post(f"{API}/applications/{tracking}/documents", files=files, data=data)
        assert r.status_code == 400

    def test_payment_initiate_sandbox(self, api_client, tracking):
        r = api_client.post(f"{API}/payments/initiate", json={"tracking_no": tracking})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["sandbox"] is True
        assert "checkout_url" in data
        assert "transaction_id" in data

    def test_payment_confirm_success(self, api_client, tracking):
        r = api_client.post(f"{API}/payments/confirm", json={"tracking_no": tracking, "success": True})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_track_after_payment(self, api_client, tracking):
        r = api_client.get(f"{API}/track/{tracking}")
        assert r.status_code == 200
        data = r.json()
        assert data["tracking_no"] == tracking
        assert data["status"] == "submitted"
        assert data["paid_at"] is not None

    def test_payment_reinitiate_after_paid(self, api_client, tracking):
        r = api_client.post(f"{API}/payments/initiate", json={"tracking_no": tracking})
        assert r.status_code == 400

    def test_admin_kpis_reflect_application(self, api_client, auth_headers, tracking):
        r = api_client.get(f"{API}/admin/kpis", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert data["submitted"] >= 1
        assert data["revenue_usd"] >= 400.0
        assert data["express_count"] >= 1

    def test_admin_applications_list(self, api_client, auth_headers, tracking):
        r = api_client.get(f"{API}/admin/applications?status=all", headers=auth_headers)
        assert r.status_code == 200
        rows = r.json()
        assert any(a["tracking_no"] == tracking for a in rows)

        r_sub = api_client.get(f"{API}/admin/applications?status=submitted", headers=auth_headers)
        assert r_sub.status_code == 200
        assert any(a["tracking_no"] == tracking for a in r_sub.json())

        r_done = api_client.get(f"{API}/admin/applications?status=done", headers=auth_headers)
        assert r_done.status_code == 200
        assert not any(a["tracking_no"] == tracking for a in r_done.json())

    def test_admin_transition_in_progress_then_done(self, api_client, auth_headers, tracking):
        # in_progress
        r = api_client.post(
            f"{API}/admin/applications/{tracking}/status",
            json={"status": "in_progress"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        # done
        r = api_client.post(
            f"{API}/admin/applications/{tracking}/status",
            json={"status": "done"},
            headers=auth_headers,
        )
        assert r.status_code == 200

        # Check log has entries
        log = api_client.get(f"{API}/admin/email-log", headers=auth_headers)
        assert log.status_code == 200
        entries = log.json()
        assert any(e.get("template_name") == "submitted" for e in entries)
        assert any(e.get("template_name") == "in_progress" for e in entries)
        assert any(e.get("template_name") == "done" for e in entries)

    def test_admin_invalid_status(self, api_client, auth_headers, tracking):
        r = api_client.post(
            f"{API}/admin/applications/{tracking}/status",
            json={"status": "bogus"},
            headers=auth_headers,
        )
        assert r.status_code == 400


# ────────────────── ADMIN SETTINGS ──────────────────
class TestAdminSettings:
    def test_get_settings(self, api_client, auth_headers):
        r = api_client.get(f"{API}/admin/settings", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "visa_types" in data
        assert "hubtel" in data

    def test_visa_price_update(self, api_client, auth_headers):
        r = api_client.post(
            f"{API}/admin/settings/visa-price",
            json={"code": "tourist_30", "price_usd": 350.0},
            headers=auth_headers,
        )
        assert r.status_code == 200

    def test_visa_price_unknown(self, api_client, auth_headers):
        r = api_client.post(
            f"{API}/admin/settings/visa-price",
            json={"code": "unknown", "price_usd": 100.0},
            headers=auth_headers,
        )
        assert r.status_code == 404

    def test_express_surcharge(self, api_client, auth_headers):
        r = api_client.post(
            f"{API}/admin/settings/express-surcharge",
            json={"price_usd": 50.0},
            headers=auth_headers,
        )
        assert r.status_code == 200

    def test_cannot_deactivate_always_active(self, api_client, auth_headers):
        r = api_client.post(
            f"{API}/admin/settings/visa-toggle",
            json={"code": "tourist_30", "active": False},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_toggle_visa_ok(self, api_client, auth_headers):
        # toggle extended_60 on then off
        r = api_client.post(
            f"{API}/admin/settings/visa-toggle",
            json={"code": "extended_60", "active": True},
            headers=auth_headers,
        )
        assert r.status_code == 200
        r = api_client.post(
            f"{API}/admin/settings/visa-toggle",
            json={"code": "extended_60", "active": False},
            headers=auth_headers,
        )
        assert r.status_code == 200

    def test_payment_toggle(self, api_client, auth_headers):
        r = api_client.post(
            f"{API}/admin/settings/payment-toggle",
            json={"code": "usdt_trc20", "active": True},
            headers=auth_headers,
        )
        assert r.status_code == 200
        # Restore
        api_client.post(
            f"{API}/admin/settings/payment-toggle",
            json={"code": "usdt_trc20", "active": False},
            headers=auth_headers,
        )

    def test_hubtel_config_update(self, api_client, auth_headers):
        r = api_client.post(
            f"{API}/admin/settings/hubtel",
            json={
                "sandbox": False,
                "api_id": "TEST_ID",
                "api_key": "TEST_KEY",
                "merchant_account_id": "TEST_MERCHANT",
                "callback_url": "https://cb.example.com",
                "return_url": "https://return.example.com",
                "outbound_proxy_url": "",
            },
            headers=auth_headers,
        )
        assert r.status_code == 200
        # Restore sandbox
        api_client.post(
            f"{API}/admin/settings/hubtel",
            json={"sandbox": True, "api_id": "", "api_key": "", "merchant_account_id": "", "callback_url": "", "return_url": "", "outbound_proxy_url": ""},
            headers=auth_headers,
        )

    def test_whatsapp_update(self, api_client, auth_headers):
        r = api_client.post(
            f"{API}/admin/settings/whatsapp",
            json={"whatsapp_admin": "+233123456789"},
            headers=auth_headers,
        )
        assert r.status_code == 200

    def test_ai_model_update(self, api_client, auth_headers):
        r = api_client.post(
            f"{API}/admin/settings/ai-model",
            json={"ai_model": "claude-sonnet-4-5-20250929"},
            headers=auth_headers,
        )
        assert r.status_code == 200

    def test_upload_limit_update(self, api_client, auth_headers):
        r = api_client.post(
            f"{API}/admin/settings/upload-limit",
            json={"max_upload_mb": 8},
            headers=auth_headers,
        )
        assert r.status_code == 200


# ────────────────── EMAIL TEMPLATES ──────────────────
class TestEmailTemplates:
    def test_list_templates(self, api_client, auth_headers):
        r = api_client.get(f"{API}/admin/email-templates", headers=auth_headers)
        assert r.status_code == 200
        rows = r.json()
        names = {(t["template_name"], t["lang"]) for t in rows}
        assert ("submitted", "en") in names
        assert ("in_progress", "en") in names
        assert ("done", "en") in names

    def test_save_template(self, api_client, auth_headers):
        r = api_client.post(
            f"{API}/admin/email-templates",
            json={
                "template_name": "submitted",
                "lang": "en",
                "subject": "TEST subject {{tracking}}",
                "html": "<p>TEST body {{name}}</p>",
            },
            headers=auth_headers,
        )
        assert r.status_code == 200
        # Verify persistence
        r2 = api_client.get(f"{API}/admin/email-templates", headers=auth_headers)
        found = [t for t in r2.json() if t["template_name"] == "submitted" and t["lang"] == "en"]
        assert found
        assert found[0]["subject"] == "TEST subject {{tracking}}"


# ────────────────── AMA CHAT ──────────────────
class TestAmaChat:
    def test_chat(self, api_client):
        r = api_client.post(
            f"{API}/chat",
            json={"message": "How long does the Ghana visa on arrival take with regular processing?"},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data.get("reply"), str)
        assert len(data["reply"]) > 5
        assert "session_id" in data
