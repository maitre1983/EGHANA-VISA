# Iteration 26: payment gateway secrets masking (Hubtel + NOWPayments) — write-only secrets, keep-on-empty, audit redaction.
# SAFETY: backs up settings.nowpayments + settings.hubtel from Mongo and restores them EXACTLY at module teardown.
import os
import copy
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
MDB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

NP_SECRETS = ("api_key", "ipn_secret", "sandbox_api_key", "sandbox_ipn_secret")
HB_SECRETS = ("api_id", "api_key", "outbound_proxy_url")


def _settings():
    return MDB.settings.find_one({"id": "singleton"}, {"_id": 0})


@pytest.fixture(scope="module", autouse=True)
def backup_restore():
    s = _settings()
    bk = {"nowpayments": copy.deepcopy(s.get("nowpayments")), "hubtel": copy.deepcopy(s.get("hubtel"))}
    yield bk
    MDB.settings.update_one({"id": "singleton"}, {"$set": {"nowpayments": bk["nowpayments"], "hubtel": bk["hubtel"]}})
    after = _settings()
    assert after["nowpayments"] == bk["nowpayments"]
    assert after["hubtel"] == bk["hubtel"]


@pytest.fixture(scope="module")
def admin():
    r = requests.post(f"{BASE_URL}/api/admin/login", json={"email": "admin@eghanavisa.com", "password": "Admin@2026"})
    if r.status_code != 200:
        pytest.skip(f"admin login failed {r.status_code}")
    tok = r.json().get("token") or r.json().get("access_token")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# --- GET redaction ---
class TestGetRedaction:
    def test_unauth_401(self):
        r = requests.get(f"{BASE_URL}/api/admin/settings")
        assert r.status_code in (401, 403)

    def test_np_redacted(self, admin, backup_restore):
        r = admin.get(f"{BASE_URL}/api/admin/settings")
        assert r.status_code == 200
        np = r.json()["nowpayments"]
        raw = backup_restore["nowpayments"]
        for f in NP_SECRETS:
            assert np[f] == ""
            v = (raw.get(f) or "").strip()
            assert np[f"{f}_set"] is bool(v)
            if len(v) >= 8:
                assert np[f"{f}_hint"] == f"••••{v[-4:]}"
        assert np["sandbox"] == raw["sandbox"]

    def test_hubtel_redacted_nonsecret_present(self, admin):
        h = admin.get(f"{BASE_URL}/api/admin/settings").json()["hubtel"]
        for f in HB_SECRETS:
            assert h[f] == "" and f"{f}_set" in h and f"{f}_hint" in h
        for f in ("sandbox", "merchant_account_id", "callback_url", "return_url", "cancellation_url"):
            assert f in h

    def test_raw_values_not_in_body(self, admin, backup_restore):
        body = admin.get(f"{BASE_URL}/api/admin/settings").text
        for sec, fields in (("nowpayments", NP_SECRETS), ("hubtel", HB_SECRETS)):
            for f in fields:
                v = (backup_restore[sec] or {}).get(f) or ""
                if len(v) >= 6:
                    assert v not in body, f"{sec}.{f} leaked"


# --- NOWPayments save keep / replace ---
class TestNowPaymentsSave:
    def test_empty_save_keeps_secrets(self, admin, backup_restore):
        bk = backup_restore["nowpayments"]
        r = admin.post(f"{BASE_URL}/api/admin/settings/nowpayments", json={
            "sandbox": bk["sandbox"], "api_key": "", "ipn_secret": "", "sandbox_api_key": "", "sandbox_ipn_secret": ""})
        assert r.status_code == 200
        after = _settings()["nowpayments"]
        for f in NP_SECRETS:
            assert (after.get(f) or "") == (bk.get(f) or ""), f
        assert after["sandbox"] == bk["sandbox"]

    def test_whitespace_save_keeps_secrets(self, admin, backup_restore):
        bk = backup_restore["nowpayments"]
        r = admin.post(f"{BASE_URL}/api/admin/settings/nowpayments", json={"sandbox": bk["sandbox"], "api_key": "   "})
        assert r.status_code == 200
        assert _settings()["nowpayments"]["api_key"] == bk["api_key"]

    def test_new_value_replaces_only_that_field(self, admin, backup_restore):
        bk = backup_restore["nowpayments"]
        r = admin.post(f"{BASE_URL}/api/admin/settings/nowpayments", json={
            "sandbox": bk["sandbox"], "sandbox_api_key": "  TEST_sbxkey_ABCD9999  "})
        assert r.status_code == 200
        after = _settings()["nowpayments"]
        assert after["sandbox_api_key"] == "TEST_sbxkey_ABCD9999"
        for f in ("api_key", "ipn_secret", "sandbox_ipn_secret"):
            assert (after.get(f) or "") == (bk.get(f) or "")
        np = admin.get(f"{BASE_URL}/api/admin/settings").json()["nowpayments"]
        assert np["sandbox_api_key"] == "" and np["sandbox_api_key_set"] is True
        assert np["sandbox_api_key_hint"] == "••••9999"
        # restore immediately
        MDB.settings.update_one({"id": "singleton"}, {"$set": {"nowpayments": bk}})
        assert _settings()["nowpayments"] == bk

    def test_np_test_connection_still_ok(self, admin):
        r = admin.post(f"{BASE_URL}/api/admin/settings/nowpayments/test")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True and d["mode"] == "production"


# --- Hubtel save keep / replace ---
class TestHubtelSave:
    def test_hubtel_set_then_keep(self, admin, backup_restore):
        bk = backup_restore["hubtel"]
        base = {k: bk.get(k, "") for k in ("merchant_account_id", "callback_url", "return_url", "cancellation_url")}
        r = admin.post(f"{BASE_URL}/api/admin/settings/hubtel", json={
            "sandbox": True, **base, "api_id": "TEST_hubid_1111", "api_key": "TEST_hubkey_2222",
            "outbound_proxy_url": "http://TEST_user:TEST_pw@proxy.invalid:3128"})
        assert r.status_code == 200
        st = _settings()["hubtel"]
        assert st["api_id"] == "TEST_hubid_1111" and st["api_key"] == "TEST_hubkey_2222"
        g = admin.get(f"{BASE_URL}/api/admin/settings")
        h = g.json()["hubtel"]
        assert h["api_id"] == "" and h["api_id_hint"] == "••••1111"
        assert h["outbound_proxy_url"] == "" and h["outbound_proxy_url_set"] is True
        assert "TEST_hubkey_2222" not in g.text and "TEST_pw" not in g.text
        # empty save keeps
        r = admin.post(f"{BASE_URL}/api/admin/settings/hubtel", json={"sandbox": True, **base})
        assert r.status_code == 200
        st2 = _settings()["hubtel"]
        assert st2["api_id"] == "TEST_hubid_1111" and st2["api_key"] == "TEST_hubkey_2222"
        assert st2["outbound_proxy_url"] == "http://TEST_user:TEST_pw@proxy.invalid:3128"
        assert st2["sandbox"] is True

    def test_audit_log_redacted(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/audit-log", params={"search": "/api/admin/settings/", "page_size": 30})
        assert r.status_code == 200
        items = r.json()["items"]
        hub = [i for i in items if i["path"] == "/api/admin/settings/hubtel" and (i.get("details") or {}).get("api_id")]
        assert hub, "no hubtel audit entry"
        d = hub[0]["details"]
        assert d["api_id"] == "***" and d["api_key"] == "***" and d["outbound_proxy_url"] == "***"
        npi = [i for i in items if i["path"] == "/api/admin/settings/nowpayments" and (i.get("details") or {}).get("sandbox_api_key")]
        assert npi and npi[0]["details"]["sandbox_api_key"] == "***"
        text = r.text
        for v in ("TEST_hubid_1111", "TEST_hubkey_2222", "TEST_pw", "TEST_sbxkey_ABCD9999"):
            assert v not in text

    def test_restore_hubtel(self, backup_restore):
        MDB.settings.update_one({"id": "singleton"}, {"$set": {"hubtel": backup_restore["hubtel"]}})
        assert _settings()["hubtel"] == backup_restore["hubtel"]


# --- Diagnostics leak check ---
class TestDiagnostics:
    def test_diagnostics_no_secrets(self, admin, backup_restore):
        r = admin.post(f"{BASE_URL}/api/admin/payments/diagnostics", json={"tracking_nos": []}, timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "hubtel" in d and "nowpayments" in d
        for sec, fields in (("nowpayments", NP_SECRETS), ("hubtel", HB_SECRETS)):
            for f in fields:
                v = (backup_restore[sec] or {}).get(f) or ""
                if len(v) >= 6:
                    assert v not in r.text
        assert d["nowpayments"]["live_keys"]["keys_present"] is True
