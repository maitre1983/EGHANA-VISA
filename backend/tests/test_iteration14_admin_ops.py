# Iteration 14: SMS alerts, gateway health monitoring, audit log, support tickets admin
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN = {"email": "admin@eghanavisa.com", "password": "Admin@2026"}


def _env():
    env = {}
    with open("/app/backend/.env") as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                env[k] = v.strip('"')
    return env


ENV = _env()
CRON = ENV["WEBHOOK_CRON_SECRET"]


@pytest.fixture(scope="module")
def mdb():
    return MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]


@pytest.fixture(scope="module")
def H():
    r = requests.post(f"{BASE_URL}/api/admin/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.skip("admin login failed")
    return {"Authorization": f"Bearer {r.json()['token']}"}


EMPTY_SMS = {"enabled": False, "client_id": "", "client_secret": "", "sender_id": "",
             "admin_numbers": [], "events": {"new_submission": True, "payment_success": True, "ticket_escalated": True}}


# ---- Support tickets ----
@pytest.fixture(scope="module", autouse=True)
def seed_ticket(mdb):
    """Self-contained fixture: tests no longer depend on a pre-existing DB ticket."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    mdb.support_tickets.update_one({"id": "test-ticket-1"}, {"$set": {
        "id": "test-ticket-1", "session_id": "test-session-1", "status": "open", "priority": "normal",
        "customer_name": "TEST Visitor", "customer_email": "test-visitor@example.com", "tracking_no": "",
        "question": "TEST question", "ai_reply": "TEST reply", "created_at": now, "updated_at": now,
        "admin_reply": None, "admin_replied_at": None}}, upsert=True)
    mdb.chat_log.update_one({"id": "test-chat-1"}, {"$set": {
        "id": "test-chat-1", "session_id": "test-session-1", "user_message": "TEST question",
        "ai_reply": "TEST reply", "escalated": True, "ticket_id": "test-ticket-1", "created_at": now}}, upsert=True)
    yield
    mdb.support_tickets.delete_one({"id": "test-ticket-1"})
    mdb.chat_log.delete_one({"id": "test-chat-1"})

class TestTickets:
    def test_list_filters(self, H):
        r = requests.get(f"{BASE_URL}/api/admin/support-tickets", headers=H, timeout=30)
        assert r.status_code == 200
        assert any(t["id"] == "test-ticket-1" for t in r.json())
        r2 = requests.get(f"{BASE_URL}/api/admin/support-tickets?status=resolved", headers=H, timeout=30)
        assert all(t["status"] == "resolved" for t in r2.json())

    def test_conversation(self, H):
        r = requests.get(f"{BASE_URL}/api/admin/support-tickets/test-ticket-1/conversation", headers=H, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["ticket"]["id"] == "test-ticket-1"
        assert isinstance(d["messages"], list) and len(d["messages"]) >= 1
        assert "_id" not in d["ticket"]

    def test_conversation_404(self, H):
        r = requests.get(f"{BASE_URL}/api/admin/support-tickets/nope-xyz/conversation", headers=H, timeout=30)
        assert r.status_code == 404

    def test_status_invalid(self, H):
        r = requests.post(f"{BASE_URL}/api/admin/support-tickets/test-ticket-1/status", json={"status": "bogus"}, headers=H, timeout=30)
        assert r.status_code == 400

    def test_reply_then_reopen(self, H, mdb):
        before = time.time()
        r = requests.post(f"{BASE_URL}/api/admin/support-tickets/test-ticket-1/reply",
                          json={"reply": "TEST_reply: passport must be valid 6 months."}, headers=H, timeout=60)
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True, "emailed": True}
        t = mdb.support_tickets.find_one({"id": "test-ticket-1"})
        assert t["status"] == "resolved" and t["admin_reply"].startswith("TEST_reply")
        time.sleep(2)
        log = mdb.email_log.find_one({"template_name": "support_reply"}, sort=[("created_at", -1)])
        assert log is not None, "no email_log entry for support_reply"
        print("email_log entry:", {k: log.get(k) for k in ("template_name", "recipient", "status", "created_at", "error")})
        # reopen
        r = requests.post(f"{BASE_URL}/api/admin/support-tickets/test-ticket-1/status", json={"status": "open"}, headers=H, timeout=30)
        assert r.status_code == 200
        assert mdb.support_tickets.find_one({"id": "test-ticket-1"})["status"] == "open"

    def test_status_404(self, H):
        r = requests.post(f"{BASE_URL}/api/admin/support-tickets/nope-xyz/status", json={"status": "open"}, headers=H, timeout=30)
        assert r.status_code == 404

    def test_requires_auth(self):
        assert requests.get(f"{BASE_URL}/api/admin/support-tickets", timeout=30).status_code in (401, 403)


# ---- Gateway health ----
class TestHealth:
    def test_check_now_and_get(self, H):
        r = requests.post(f"{BASE_URL}/api/admin/health/check", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        gws = {x["gateway"]: x for x in d["results"]}
        assert "hubtel" in gws and "nowpayments" in gws
        print("health:", d)
        g = requests.get(f"{BASE_URL}/api/admin/health", headers=H, timeout=30).json()
        for k in ("latest", "history", "uptime_pct", "payments_24h", "last_paid"):
            assert k in g
        assert g["latest"]["checked_at"] == d["checked_at"]

    def test_cron_auth(self):
        assert requests.post(f"{BASE_URL}/api/cron/gateway-health", timeout=30).status_code == 401
        assert requests.post(f"{BASE_URL}/api/cron/gateway-health", headers={"Authorization": "Bearer wrong"}, timeout=30).status_code == 401

    def test_cron_ok_and_duplicate(self, mdb):
        n0 = mdb.gateway_health.count_documents({})
        wid = f"TEST_{uuid.uuid4()}"
        h = {"Authorization": f"Bearer {CRON}", "X-Webhook-Id": wid}
        t0 = time.time()
        r = requests.post(f"{BASE_URL}/api/cron/gateway-health", headers=h, json={}, timeout=30)
        assert r.status_code == 200 and r.json()["accepted"] == wid
        print("cron ack seconds", round(time.time() - t0, 2))
        r2 = requests.post(f"{BASE_URL}/api/cron/gateway-health", headers=h, json={}, timeout=30)
        assert r2.status_code == 200 and r2.json().get("duplicate") is True
        time.sleep(12)
        assert mdb.gateway_health.count_documents({}) > n0
        mdb.cron_runs.delete_one({"run_id": wid})


# ---- Audit log ----
class TestAudit:
    def test_audit_log(self, H):
        requests.post(f"{BASE_URL}/api/admin/login", json={"email": ADMIN["email"], "password": "WrongPass_TEST"}, timeout=30)
        time.sleep(1)
        r = requests.get(f"{BASE_URL}/api/admin/audit-log?page=1&page_size=5", headers=H, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["page_size"] == 5 and len(d["items"]) <= 5 and d["total"] >= 1
        assert ADMIN["email"] in d["admins"]
        f = requests.get(f"{BASE_URL}/api/admin/audit-log?only_failed=true&search=login", headers=H, timeout=30).json()
        assert f["items"], "failed login not logged"
        it = f["items"][0]
        assert it["success"] is False and it["details"]["password"] == "***"
        assert it["admin_email"] == ADMIN["email"]
        print("ip:", it.get("ip"))
        p2 = requests.get(f"{BASE_URL}/api/admin/audit-log?page=2&page_size=5", headers=H, timeout=30).json()
        if d["total"] > 5:
            assert {i["id"] for i in p2["items"]}.isdisjoint({i["id"] for i in d["items"]})


# ---- SMS settings & dispatch ----
class TestSms:
    def test_validation_and_normalize(self, H, mdb):
        u = f"{BASE_URL}/api/admin/settings/sms"
        r = requests.post(u, json={**EMPTY_SMS, "enabled": True, "client_id": "x"}, headers=H, timeout=30)
        assert r.status_code == 400
        r = requests.post(u, json={**EMPTY_SMS, "sender_id": "ABCDEFGHIJKL"}, headers=H, timeout=30)
        assert r.status_code == 400
        r = requests.post(u, json={**EMPTY_SMS, "client_id": "TEST_fake", "client_secret": "TEST_fakesecret",
                                   "sender_id": "eGhanaVisa", "admin_numbers": ["0241234567"]}, headers=H, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["sms"]["admin_numbers"] == ["233241234567"]
        s = requests.get(f"{BASE_URL}/api/admin/settings", headers=H, timeout=30).json()["sms"]
        assert s["client_secret"] == "" and s["client_secret_set"] is True
        # empty secret keeps stored
        r = requests.post(u, json={**EMPTY_SMS, "client_id": "TEST_fake", "client_secret": "",
                                   "sender_id": "eGhanaVisa", "admin_numbers": ["+233240000201"]}, headers=H, timeout=30)
        assert r.status_code == 200
        assert mdb.settings.find_one({"id": "singleton"})["sms"]["client_secret"] == "TEST_fakesecret"

    def test_enable_and_dispatch(self, H, mdb):
        u = f"{BASE_URL}/api/admin/settings/sms"
        try:
            r = requests.post(u, json={**EMPTY_SMS, "enabled": True, "client_id": "TEST_fake", "client_secret": "TEST_fakesecret",
                                       "sender_id": "eGhanaVisa", "admin_numbers": ["+233240000201"]}, headers=H, timeout=30)
            assert r.status_code == 200, r.text
            t = requests.post(f"{BASE_URL}/api/admin/sms/test", headers=H, timeout=60)
            assert t.status_code == 200, t.text
            td = t.json()
            print("sms test:", td)
            assert td["ok"] is False and td["results"][0]["error"]
            log = requests.get(f"{BASE_URL}/api/admin/sms-log", headers=H, timeout=30).json()
            assert log and log[0]["id"] == td["results"][0]["id"]
            # application creation -> new_submission sms
            payload = {"visa_code": "tourist_evisa", "passport_country": "France",
                       "passport_number": f"TST{uuid.uuid4().hex[:6].upper()}", "passport_type": "ordinary",
                       "passport_expiry": "2030-01-01", "travelling_from": "France", "arrival_date": "2026-06-01",
                       "departure_date": "2026-06-15", "full_name": "TEST_ Sms Iter14", "email": "test.iter14@example.com",
                       "phone": "+33612345678", "profession": "Engineer", "processing": "regular", "lang": "en"}
            t0 = time.time()
            a = requests.post(f"{BASE_URL}/api/applications", json=payload, timeout=60)
            el = time.time() - t0
            assert a.status_code == 200, a.text
            trk = a.json()["tracking_no"]
            print("app created", trk, "in", round(el, 2), "s")
            time.sleep(4)
            e = mdb.sms_log.find_one({"event": "new_submission", "content": {"$regex": trk}})
            assert e is not None and e["ok"] is False
            print("new_submission sms_log:", e.get("error"))
            d = requests.delete(f"{BASE_URL}/api/admin/applications/{trk}", headers=H, timeout=30)
            print("delete app", d.status_code)
        finally:
            r = requests.post(u, json=EMPTY_SMS, headers=H, timeout=30)
            assert r.status_code == 200
            mdb.settings.update_one({"id": "singleton"}, {"$set": {"sms.client_secret": ""}})
            s = mdb.settings.find_one({"id": "singleton"})["sms"]
            assert s["enabled"] is False and s["client_secret"] == "" and s["client_id"] == ""
