"""Iteration 4 — Code-quality remediation regression tests.

Focus:
  1. Email template variable substitution regression after `_TPL_OPEN/_TPL_CLOSE` refactor
  2. Broad smoke regression on health, config, applications, admin login, USDT toggle & simulation, chat
"""
import os
import io
import time
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE_URL:
    # fallback to frontend .env
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
            break

API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@eghanavisa.com"
ADMIN_PASSWORDS = ["Admin@2026New!", "Admin@2026"]


@pytest.fixture(scope="module")
def admin_token():
    for pw in ADMIN_PASSWORDS:
        r = requests.post(f"{API}/admin/login", json={"email": ADMIN_EMAIL, "password": pw}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get("must_change_password"):
                # Handle force password change
                r2 = requests.post(
                    f"{API}/admin/change-password",
                    headers={"Authorization": f"Bearer {data['token']}"},
                    json={"current_password": pw, "new_password": "Admin@2026New!"},
                    timeout=15,
                )
                if r2.status_code == 200:
                    return r2.json().get("token") or data["token"]
            return data["token"]
    pytest.skip(f"Admin login failed for all passwords tried")


# ---------- Health / Config ----------

APP_PAYLOAD_TEMPLATE = {
    "visa_code": "tourist_30",
    "passport_country": "USA",
    "passport_number": "TESTPP001",
    "passport_type": "ordinary",
    "passport_expiry": "2030-01-01",
    "travelling_from": "USA",
    "arrival_date": "2026-06-01",
    "departure_date": "2026-06-15",
    "full_name": "TEST John Doe",
    "email": "test.john@example.com",
    "phone": "+233200000001",
    "profession": "Engineer",
    "processing": "regular",
    "lang": "en",
}


class TestHealthAndConfig:
    def test_config_public(self):
        r = requests.get(f"{API}/config", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "payment_methods" in data
        assert isinstance(data["payment_methods"], list)


# ---------- Applications submission ----------

class TestApplicationsFlow:
    def test_create_application(self):
        payload = dict(APP_PAYLOAD_TEMPLATE)
        r = requests.post(f"{API}/applications", json=payload, timeout=20)
        assert r.status_code in (200, 201), f"got {r.status_code} {r.text[:300]}"
        data = r.json()
        assert "tracking_no" in data
        # Save for later
        pytest.tracking_no = data["tracking_no"]

    def test_track_application(self):
        tn = getattr(pytest, "tracking_no", None)
        if not tn:
            pytest.skip("Need tracking_no from prior test")
        r = requests.get(f"{API}/track/{tn}", timeout=10)
        assert r.status_code == 200
        assert r.json().get("tracking_no") == tn


# ---------- Admin auth ----------

class TestAdminAuth:
    def test_admin_login(self, admin_token):
        assert isinstance(admin_token, str)
        assert len(admin_token) > 10


# ---------- Email template substitution (regression for _TPL_OPEN/_TPL_CLOSE refactor) ----------

class TestEmailTemplateSubstitution:
    """After iteration 4 refactor, EmailService uses `{{name}}` delimiter.
    Templates in DB have MIXED delimiters (some `{name}`, some `{{name}}`) — verify substitution."""

    @pytest.mark.anyio
    async def test_render_substitutes_all_placeholders(self):
        from motor.motor_asyncio import AsyncIOMotorClient
        from dotenv import dotenv_values
        cfg = dotenv_values("/app/backend/.env")
        client = AsyncIOMotorClient(cfg["MONGO_URL"].strip('"'))
        db = client[cfg["DB_NAME"].strip('"')]
        import sys
        sys.path.insert(0, "/app/backend")
        from email_service import EmailService
        svc = EmailService(db)
        ctx = {"name": "John Doe", "tracking": "TRK-TEST-42", "visa_type": "Tourist",
               "processing": "Standard", "amount": "150"}
        failed = []
        for tpl in ["submitted", "in_progress", "done"]:
            subj, html = await svc.render_template(tpl, "en", ctx)
            # After render, NO {name} or {tracking} placeholder should remain (single or double brace)
            import re
            text = subj + " " + html
            # find any brace-token that survived
            leftover = re.findall(r'\{\{?[a-zA-Z_]+\}?\}', text)
            if leftover:
                failed.append((tpl, leftover))
        assert not failed, f"Unsubstituted placeholders remain in templates: {failed}"


# ---------- USDT simulation regression ----------

class TestUsdtSimulation:
    def test_toggle_and_simulate(self, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        # Enable trc20
        r = requests.post(f"{API}/admin/settings/payment-toggle",
                          json={"code": "usdt_trc20", "active": True},
                          headers=h, timeout=15)
        assert r.status_code == 200, r.text
        # Create application
        payload = dict(APP_PAYLOAD_TEMPLATE)
        payload["passport_number"] = "TESTUSDT01"
        payload["email"] = "test.usdt@example.com"
        r = requests.post(f"{API}/applications", json=payload, timeout=20)
        assert r.status_code in (200, 201)
        tn = r.json()["tracking_no"]
        # Initiate crypto — should return simulation payload since NP unconfigured
        r = requests.post(f"{API}/payments/crypto/initiate",
                          json={"tracking_no": tn, "network": "trc20"}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("simulated") is True
        pid = data["payment_id"]
        # Simulate success
        r = requests.post(f"{API}/payments/crypto/simulate-finish/{pid}",
                          json={"success": True}, timeout=15)
        assert r.status_code == 200, r.text
        # Verify tracking is paid+submitted
        r = requests.get(f"{API}/track/{tn}", timeout=10)
        assert r.status_code == 200
        assert r.json().get("payment_status") in ("paid", "submitted", "completed") or \
               r.json().get("status") in ("submitted", "in_progress", "done")


# ---------- Ama chat ----------

class TestAmaChat:
    def test_chat_returns_reply(self):
        r = requests.post(f"{API}/chat", json={"message": "How much is a Ghana visa?", "session_id": None}, timeout=45)
        # AI may be slow but shouldn't 5xx
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert "reply" in data
        assert isinstance(data["reply"], str) and len(data["reply"]) > 0
