# Iteration 24 — extended production payment guards (Host spoof variants, failure callbacks,
# preview sandbox regression). Never calls crypto initiate (preview NOWPayments is LIVE-configured).
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
LOCAL = "http://localhost:8001"
ADMIN = {"email": "admin@eghanavisa.com", "password": "Admin@2026"}
CREATED = []

NON_PREVIEW_HOSTS = [
    "eghanavisa.com",
    "www.eghanavisa.com",
    "EGHANAVISA.COM:443",
    "evil.preview.emergentagent.com.attacker.com",
    "preview.emergentagent.com",  # bare suffix without leading label
    "",
]


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    r = requests.post(f"{BASE_URL}/api/admin/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        return
    tok = r.json().get("token") or r.json().get("access_token")
    for trk in CREATED:
        requests.delete(f"{BASE_URL}/api/admin/applications/{trk}", headers={"Authorization": f"Bearer {tok}"}, timeout=30)


def _create():
    p = {
        "visa_code": "tourist_evisa", "passport_country": "France", "passport_number": "TEST12345",
        "passport_type": "Ordinary", "passport_expiry": "2030-01-01", "travelling_from": "France",
        "arrival_date": "2027-02-01", "departure_date": "2027-02-15", "full_name": "TEST_Guard User",
        "email": "delivered@resend.dev", "phone": "+33600000000", "profession": "Engineer",
        "processing": "regular", "lang": "en",
    }
    r = requests.post(f"{BASE_URL}/api/applications", json=p, timeout=30)
    assert r.status_code == 200, r.text
    trk = r.json()["tracking_no"]
    CREATED.append(trk)
    return trk


def _status(trk):
    return requests.get(f"{BASE_URL}/api/payments/status/{trk}", timeout=30).json()["payment_status"]


@pytest.mark.parametrize("host", NON_PREVIEW_HOSTS)
def test_confirm_refused_for_non_preview_host_variants(host):
    trk = _create()
    r = requests.post(f"{LOCAL}/api/payments/confirm", json={"tracking_no": trk, "success": True},
                      headers={"Host": host} if host else {"Host": ""}, timeout=30)
    assert r.status_code in (403, 400), (host, r.status_code, r.text)
    assert _status(trk) != "paid"


def test_x_forwarded_host_spoof_ignored():
    trk = _create()
    r = requests.post(f"{LOCAL}/api/payments/confirm", json={"tracking_no": trk, "success": True},
                      headers={"Host": "eghanavisa.com", "X-Forwarded-Host": "x.preview.emergentagent.com"}, timeout=30)
    assert r.status_code == 403
    assert _status(trk) != "paid"


def test_initiate_suspended_message_readable():
    trk = _create()
    r = requests.post(f"{LOCAL}/api/payments/initiate", json={"tracking_no": trk}, headers={"Host": "eghanavisa.com"}, timeout=30)
    assert r.status_code == 503
    d = r.json()["detail"]
    assert d["code"] == "payments_suspended" and "temporarily unavailable" in d["message"]
    # no transaction id written
    assert _status(trk) == "pending" or _status(trk) != "paid"


def test_forged_failed_callback_does_not_flip_status_on_prod():
    trk = _create()
    body = {"ResponseCode": "2001", "Status": "Failed", "Data": {"ClientReference": trk, "Status": "Failed", "CheckoutId": "FORGED"}}
    r = requests.post(f"{LOCAL}/api/webhooks/hubtel", json=body, headers={"Host": "eghanavisa.com"}, timeout=30)
    assert r.status_code == 200
    time.sleep(3)
    assert _status(trk) not in ("paid", "failed")


def test_forged_success_callback_top_level_shape_on_prod():
    trk = _create()
    body = {"ResponseCode": "0000", "Status": "Success", "ClientReference": trk}
    assert requests.post(f"{LOCAL}/api/webhooks/hubtel", json=body, headers={"Host": "eghanavisa.com"}, timeout=30).status_code == 200
    time.sleep(3)
    assert _status(trk) != "paid"


def test_crypto_simulate_refused_prod_variants():
    for host in ("eghanavisa.com", "evil.preview.emergentagent.com.attacker.com"):
        r = requests.post(f"{LOCAL}/api/payments/crypto/simulate-finish/NP-SIM-ANY", json={"success": True},
                          headers={"Host": host}, timeout=30)
        assert r.status_code == 403, host


def test_ipn_bad_signature_rejected():
    r = requests.post(f"{LOCAL}/api/webhooks/nowpayments", json={"payment_id": "X", "payment_status": "finished"},
                      headers={"Host": "eghanavisa.com", "x-nowpayments-sig": "deadbeef"}, timeout=30)
    assert r.status_code == 401


def test_preview_host_localhost_with_preview_header_works():
    # simulates the Cloudflare worker Host header
    trk = _create()
    H = {"Host": "foo.preview.emergentcf.cloud"}
    assert requests.post(f"{LOCAL}/api/payments/initiate", json={"tracking_no": trk}, headers=H, timeout=30).status_code == 200
    r = requests.post(f"{LOCAL}/api/payments/confirm", json={"tracking_no": trk, "success": True}, headers=H, timeout=30)
    assert r.status_code == 200 and r.json()["ok"] is True
    assert _status(trk) == "paid"


def test_preview_public_sandbox_full_flow_and_failure():
    trk = _create()
    r = requests.post(f"{BASE_URL}/api/payments/initiate", json={"tracking_no": trk}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["sandbox"] is True and d["checkout_url"].startswith("/payment/sandbox")
    r = requests.post(f"{BASE_URL}/api/payments/confirm", json={"tracking_no": trk, "transaction_id": d["transaction_id"], "success": True}, timeout=30)
    assert r.status_code == 200 and r.json()["ok"] is True
    assert _status(trk) == "paid"
    # re-initiate after paid -> 400
    assert requests.post(f"{BASE_URL}/api/payments/initiate", json={"tracking_no": trk}, timeout=30).status_code == 400
    # failure path on another app
    trk2 = _create()
    r = requests.post(f"{BASE_URL}/api/payments/confirm", json={"tracking_no": trk2, "success": False}, timeout=30)
    assert r.status_code == 200 and r.json()["ok"] is False
    assert _status(trk2) == "failed"
