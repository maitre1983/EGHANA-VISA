"""Iteration 3 backend tests — USDT simulation mode when NowPayments is unconfigured.

Covers:
  - crypto_initiate returns simulated payment (200) when toggle=active + NP unconfigured
  - crypto_initiate 403 when method inactive; 404 unknown tracking; 400 already paid
  - USDT discount applied in simulation (price_amount_usd)
  - simulate-finish success → application paid + submitted + email log entry
  - simulate-finish failure → payment_status='failed'
  - simulate-finish 400 for non-simulated payment (skipped — needs real NP account)
  - crypto/status for simulated payment: no external call, current record returned
  - full e2e: create app → simulate init → simulate-finish success → tracking accessible
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

DEFAULT_ADMIN_EMAIL = "admin@eghanavisa.com"
DEFAULT_ADMIN_PASS = "Admin@2026"
NEW_ADMIN_PASS = "Admin@2026New!"


# ────────────────────── FIXTURES ──────────────────────
@pytest.fixture(scope="session")
def api_client():
    return requests.Session()


@pytest.fixture(scope="session")
def admin_token(api_client):
    r = api_client.post(f"{API}/admin/login", json={"email": DEFAULT_ADMIN_EMAIL, "password": NEW_ADMIN_PASS})
    if r.status_code == 200:
        return r.json()["token"]
    r = api_client.post(f"{API}/admin/login", json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASS})
    assert r.status_code == 200, r.text
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


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _toggle_usdt(api_client, auth_headers, code: str, active: bool):
    r = api_client.post(
        f"{API}/admin/settings/payment-toggle",
        json={"code": code, "active": active},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text


def _set_usdt_discount(api_client, auth_headers, pct: float):
    r = api_client.post(
        f"{API}/admin/settings/usdt-discount",
        json={"pct": pct},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text


def _ensure_np_unconfigured(api_client, auth_headers):
    """Clear all NowPayments keys so `is_configured` returns False."""
    r = api_client.post(
        f"{API}/admin/settings/nowpayments",
        json={
            "sandbox": True,
            "api_key": "",
            "ipn_secret": "",
            "sandbox_api_key": "",
            "sandbox_ipn_secret": "",
        },
        headers=auth_headers,
    )
    assert r.status_code == 200


def _create_app(api_client, processing="regular", visa="tourist_30"):
    payload = {
        "visa_code": visa,
        "passport_country": "France",
        "passport_number": f"TEST{uuid.uuid4().hex[:8].upper()}",
        "passport_type": "ordinary",
        "passport_expiry": "2030-12-31",
        "travelling_from": "France",
        "arrival_date": "2026-06-01",
        "departure_date": "2026-06-15",
        "full_name": "TEST USDT Sim",
        "email": "test_usdt_sim@example.com",
        "phone": "+33612345678",
        "profession": "Engineer",
        "processing": processing,
        "lang": "en",
    }
    r = api_client.post(f"{API}/applications", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def env_setup(api_client, auth_headers):
    """Activate USDT TRC20+BEP20 and ensure NP is unconfigured. Restore in teardown."""
    _ensure_np_unconfigured(api_client, auth_headers)
    _toggle_usdt(api_client, auth_headers, "usdt_trc20", True)
    _toggle_usdt(api_client, auth_headers, "usdt_bep20", True)
    _set_usdt_discount(api_client, auth_headers, 0.0)
    yield
    # teardown: return to defaults
    _toggle_usdt(api_client, auth_headers, "usdt_trc20", False)
    _toggle_usdt(api_client, auth_headers, "usdt_bep20", False)
    _set_usdt_discount(api_client, auth_headers, 0.0)


# ────────────────────── /api/config ──────────────────────
class TestPublicConfig:
    def test_config_reports_np_unconfigured(self, api_client, auth_headers, env_setup):
        r = api_client.get(f"{API}/config")
        assert r.status_code == 200
        data = r.json()
        assert data["nowpayments_configured"] is False
        # Both USDT methods should be listed as active in payment_methods
        methods = {m["code"]: m for m in data["payment_methods"]}
        assert methods["usdt_trc20"]["active"] is True
        assert methods["usdt_bep20"]["active"] is True


# ────────────────────── crypto initiate ──────────────────────
class TestCryptoInitiateSimulation:
    def test_initiate_trc20_returns_simulated(self, api_client, env_setup):
        app_doc = _create_app(api_client)
        r = api_client.post(
            f"{API}/payments/crypto/initiate",
            json={"tracking_no": app_doc["tracking_no"], "network": "trc20"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["simulated"] is True
        assert data["payment_id"].startswith("NP-SIM-")
        assert data["pay_address"].startswith("TSIMULATED")
        assert data["network"] == "trc20"
        assert data["pay_amount"] > 0

    def test_initiate_bep20_returns_simulated(self, api_client, env_setup):
        app_doc = _create_app(api_client)
        r = api_client.post(
            f"{API}/payments/crypto/initiate",
            json={"tracking_no": app_doc["tracking_no"], "network": "bep20"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["simulated"] is True
        assert data["payment_id"].startswith("NP-SIM-")
        assert data["pay_address"].startswith("0xSIMULATED")

    def test_initiate_403_when_method_inactive(self, api_client, auth_headers, env_setup):
        _toggle_usdt(api_client, auth_headers, "usdt_trc20", False)
        try:
            app_doc = _create_app(api_client)
            r = api_client.post(
                f"{API}/payments/crypto/initiate",
                json={"tracking_no": app_doc["tracking_no"], "network": "trc20"},
            )
            assert r.status_code == 403, r.text
        finally:
            _toggle_usdt(api_client, auth_headers, "usdt_trc20", True)

    def test_initiate_404_unknown_tracking(self, api_client, env_setup):
        r = api_client.post(
            f"{API}/payments/crypto/initiate",
            json={"tracking_no": "GH-2026-000000", "network": "trc20"},
        )
        assert r.status_code == 404

    def test_initiate_400_when_already_paid(self, api_client, env_setup):
        app_doc = _create_app(api_client)
        # Pay via Hubtel sandbox
        r = api_client.post(f"{API}/payments/initiate", json={"tracking_no": app_doc["tracking_no"]})
        assert r.status_code == 200
        r = api_client.post(f"{API}/payments/confirm", json={"tracking_no": app_doc["tracking_no"], "success": True})
        assert r.status_code == 200
        # Now crypto initiate should 400
        r = api_client.post(
            f"{API}/payments/crypto/initiate",
            json={"tracking_no": app_doc["tracking_no"], "network": "trc20"},
        )
        assert r.status_code == 400

    def test_initiate_400_invalid_network(self, api_client, env_setup):
        app_doc = _create_app(api_client)
        r = api_client.post(
            f"{API}/payments/crypto/initiate",
            json={"tracking_no": app_doc["tracking_no"], "network": "erc20"},
        )
        assert r.status_code == 400


# ────────────────────── USDT DISCOUNT ──────────────────────
class TestUsdtDiscount:
    def test_discount_applied_in_simulation(self, api_client, auth_headers, env_setup):
        _set_usdt_discount(api_client, auth_headers, 10.0)
        try:
            app_doc = _create_app(api_client, processing="regular", visa="tourist_30")
            assert app_doc["amount_usd"] == 350.0  # base tourist_30 price
            r = api_client.post(
                f"{API}/payments/crypto/initiate",
                json={"tracking_no": app_doc["tracking_no"], "network": "trc20"},
            )
            assert r.status_code == 200, r.text
            init = r.json()
            payment_id = init["payment_id"]
            # pay_amount should reflect 315.00 * 1.00 = 315.00
            assert init["pay_amount"] == 315.0, f"expected 315.0, got {init['pay_amount']}"

            # crypto status must not throw (simulated=true, no external call)
            r2 = api_client.get(f"{API}/payments/crypto/status/{payment_id}")
            assert r2.status_code == 200
            st = r2.json()
            assert st["payment_status"] == "waiting"
            assert st["pay_amount"] == 315.0
        finally:
            _set_usdt_discount(api_client, auth_headers, 0.0)


# ────────────────────── SIMULATE FINISH ──────────────────────
class TestSimulateFinish:
    def test_e2e_simulate_success(self, api_client, auth_headers, env_setup):
        app_doc = _create_app(api_client)
        tracking = app_doc["tracking_no"]

        # 1. Initiate
        r = api_client.post(
            f"{API}/payments/crypto/initiate",
            json={"tracking_no": tracking, "network": "trc20"},
        )
        assert r.status_code == 200
        payment_id = r.json()["payment_id"]

        # 2. Status is 'waiting'
        r = api_client.get(f"{API}/payments/crypto/status/{payment_id}")
        assert r.status_code == 200
        assert r.json()["payment_status"] == "waiting"

        # 3. Simulate finish success
        r = api_client.post(
            f"{API}/payments/crypto/simulate-finish/{payment_id}",
            json={"success": True},
        )
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

        # 4. Tracking is now accessible (was 404 before)
        r = api_client.get(f"{API}/track/{tracking}")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "submitted"
        assert data["tracking_no"] == tracking
        assert data["paid_at"] is not None

        # 5. Email log has a 'submitted' entry for this tracking
        r = api_client.get(f"{API}/admin/email-log", headers=auth_headers)
        assert r.status_code == 200
        entries = r.json()
        found = [e for e in entries if e.get("template_name") == "submitted"
                 and tracking in (e.get("context", {}) or {}).get("tracking", "")]
        # fallback: substring match on rendered subject/body
        if not found:
            found = [e for e in entries if e.get("template_name") == "submitted"
                     and tracking in str(e)]
        assert found, f"No 'submitted' email log entry for {tracking}"

        # 6. Status now reflects finished
        r = api_client.get(f"{API}/payments/crypto/status/{payment_id}")
        assert r.status_code == 200
        assert r.json()["payment_status"] == "finished"
        assert r.json()["internal_status"] == "paid"

    def test_simulate_finish_failure(self, api_client, env_setup):
        app_doc = _create_app(api_client)
        r = api_client.post(
            f"{API}/payments/crypto/initiate",
            json={"tracking_no": app_doc["tracking_no"], "network": "bep20"},
        )
        assert r.status_code == 200
        payment_id = r.json()["payment_id"]

        r = api_client.post(
            f"{API}/payments/crypto/simulate-finish/{payment_id}",
            json={"success": False},
        )
        assert r.status_code == 200

        # Status reflects failed
        r = api_client.get(f"{API}/payments/crypto/status/{payment_id}")
        assert r.status_code == 200
        assert r.json()["payment_status"] == "failed"

        # Application should NOT be paid
        r = api_client.get(f"{API}/track/{app_doc['tracking_no']}")
        assert r.status_code == 404

    def test_simulate_finish_unknown_payment(self, api_client, env_setup):
        r = api_client.post(
            f"{API}/payments/crypto/simulate-finish/NP-SIM-UNKNOWN",
            json={"success": True},
        )
        assert r.status_code == 404

    def test_simulate_finish_rejects_non_simulated(self, api_client, env_setup):
        """When crypto_payments record has simulated=false, endpoint must 400."""
        # We can't create a real NP payment (no keys), so directly seed via DB fixture is not
        # available here. Instead, indirectly check by testing a NON-existent NP-REAL id →
        # it will 404 first. This test is best-effort.
        # We rely on manual/real integration testing for the simulated=false path.
        pytest.skip("Requires real NowPayments payment record — not feasible without API keys")


# ────────────────────── STATUS ENDPOINT SKIPS POLLING FOR SIMULATED ──────────────────────
class TestCryptoStatusSkipsPolling:
    def test_status_for_simulated_returns_local(self, api_client, env_setup):
        app_doc = _create_app(api_client)
        r = api_client.post(
            f"{API}/payments/crypto/initiate",
            json={"tracking_no": app_doc["tracking_no"], "network": "trc20"},
        )
        payment_id = r.json()["payment_id"]

        # Repeated calls — no external errors even though NP is unconfigured
        for _ in range(3):
            r = api_client.get(f"{API}/payments/crypto/status/{payment_id}")
            assert r.status_code == 200
            assert r.json()["payment_status"] == "waiting"

    def test_status_unknown_payment_404(self, api_client, env_setup):
        r = api_client.get(f"{API}/payments/crypto/status/NP-DOES-NOT-EXIST")
        assert r.status_code == 404
