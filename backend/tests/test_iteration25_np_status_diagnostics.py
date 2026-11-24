# Iteration 25: NOWPayments hardening (status endpoint never 'paid' unless verified, env mismatch)
# + read-only admin payment diagnostics endpoint.
import asyncio
import os
import sys
import uuid

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _np_sandbox():
    s = mdb.settings.find_one({}, {"_id": 0, "nowpayments": 1}) or {}
    return bool((s.get("nowpayments") or {}).get("sandbox", True))


def _seed(payment_status="finished", sandbox=None, verification=None):
    trk = f"TEST-I25-{uuid.uuid4().hex[:8].upper()}"
    pid = f"TESTI25{uuid.uuid4().hex[:10]}"
    mdb.applications.insert_one({
        "tracking_no": trk, "full_name": "TEST_I25 User", "email": "delivered@resend.dev",
        "payment_status": "pending", "status": "pending_payment", "processing": "regular",
        "visa_name": "Tourist eVisa", "amount_usd": 350.0, "lang": "en",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00"})
    doc = {"payment_id": pid, "tracking_no": trk, "network": "trc20", "pay_currency": "usdttrc20",
           "pay_address": "TTEST", "pay_amount": 350.0, "price_amount_usd": 350.0,
           "payment_status": payment_status, "sandbox": _np_sandbox() if sandbox is None else sandbox,
           "simulated": False, "created_at": "2026-01-01T00:00:00+00:00", "ipn_payloads": []}
    if verification:
        doc["verification"] = verification
    mdb.crypto_payments.insert_one(doc)
    return trk, pid


@pytest.fixture
def created():
    items = []
    yield items
    for trk, pid in items:
        mdb.applications.delete_one({"tracking_no": trk})
        mdb.crypto_payments.delete_one({"payment_id": pid})


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      json={"email": "admin@eghanavisa.com", "password": "Admin@2026"}, timeout=20)
    if r.status_code != 200:
        pytest.skip("admin login failed")
    d = r.json()
    return d.get("token") or d.get("access_token")


# crypto status: finished but unverified -> processing, app not paid
def test_status_finished_unverified_is_processing(created):
    trk, pid = _seed()
    created.append((trk, pid))
    r = requests.get(f"{BASE_URL}/api/payments/crypto/status/{pid}", timeout=40)
    assert r.status_code == 200
    d = r.json()
    assert d["internal_status"] != "paid"
    assert d["internal_status"] == "processing"
    app = mdb.applications.find_one({"tracking_no": trk})
    assert app["payment_status"] != "paid"


# crypto status: finished + verification verified -> paid
def test_status_finished_verified_is_paid(created):
    trk, pid = _seed(verification={"state": "verified"})
    created.append((trk, pid))
    r = requests.get(f"{BASE_URL}/api/payments/crypto/status/{pid}", timeout=40)
    assert r.status_code == 200
    assert r.json()["internal_status"] == "paid"


# crypto status: rejected verification -> processing
def test_status_finished_rejected_is_processing(created):
    trk, pid = _seed(verification={"state": "rejected", "reasons": ["amount_received"]})
    created.append((trk, pid))
    r = requests.get(f"{BASE_URL}/api/payments/crypto/status/{pid}", timeout=40)
    assert r.status_code == 200
    assert r.json()["internal_status"] == "processing"


def test_status_unknown_404():
    r = requests.get(f"{BASE_URL}/api/payments/crypto/status/TESTI25-nonexistent", timeout=20)
    assert r.status_code == 404


# environment mismatch (settings vs payment doc) is rejected in-process, no API call
def test_verify_environment_mismatch_rejected(monkeypatch):
    import server
    called = []
    monkeypatch.setattr(server.nowp, "get_payment", lambda cfg, pid: called.append(pid) or {})
    doc = {"payment_id": "TESTI25MIS", "tracking_no": "TEST-I25-MIS", "pay_amount": 1, "simulated": False,
           "sandbox": not _np_sandbox()}
    loop = asyncio.new_event_loop()
    try:
        ver = loop.run_until_complete(server._verify_nowpayments_payment(doc))
    finally:
        loop.close()
    assert ver["state"] == "rejected"
    assert "environment_mismatch" in ver["reasons"]
    assert called == []


# diagnostics: auth required
def test_diagnostics_requires_auth():
    r = requests.post(f"{BASE_URL}/api/admin/payments/diagnostics", json={"tracking_nos": []}, timeout=20)
    assert r.status_code == 401


# diagnostics: structure + read-only on referenced application
def test_diagnostics_structure_and_read_only(admin_token, created):
    trk, pid = _seed(payment_status="waiting")
    created.append((trk, pid))
    before = mdb.applications.find_one({"tracking_no": trk}, {"_id": 0})
    before_cp = mdb.crypto_payments.find_one({"payment_id": pid}, {"_id": 0})
    settings_before = mdb.settings.find_one({}, {"_id": 0})
    r = requests.post(f"{BASE_URL}/api/admin/payments/diagnostics",
                      headers={"Authorization": f"Bearer {admin_token}"},
                      json={"tracking_nos": [trk, "TEST-I25-NOPE"]}, timeout=110)
    assert r.status_code == 200, r.text
    d = r.json()
    print(d)
    assert isinstance(d["egress_ip"], str) and d["egress_ip"]
    h = d["hubtel"]
    assert h["mode"] in ("sandbox", "live")
    assert set(h["credentials_present"]) == {"api_id", "api_key", "merchant_account_id"}
    for k in ("callback_url", "return_url", "cancellation_url", "status_api_probe", "references"):
        assert k in h
    ref = h["references"][trk]
    assert ref["local"]["payment_status"] == "pending"
    assert ref["callbacks_received"] == 0
    assert "hubtel_status_api" in ref
    assert h["references"]["TEST-I25-NOPE"]["local"] is None
    n = d["nowpayments"]
    assert n["mode"] in ("sandbox", "live")
    assert n["ipn_url"].endswith("/api/webhooks/nowpayments")
    assert "keys_present" in n["live_keys"] and "keys_present" in n["sandbox_keys"]
    if n["live_keys"]["keys_present"]:
        assert "api_key_valid" in n["live_keys"]
    after = mdb.applications.find_one({"tracking_no": trk}, {"_id": 0})
    after_cp = mdb.crypto_payments.find_one({"payment_id": pid}, {"_id": 0})
    assert after == before
    assert after_cp == before_cp
    assert mdb.settings.find_one({}, {"_id": 0}) == settings_before
