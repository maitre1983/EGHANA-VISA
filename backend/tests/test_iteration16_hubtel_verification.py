# Iteration 16 — Hubtel server-side verification (live-mode forged callback), no-downgrade of paid,
# sandbox regression, admin payment-verifications endpoints, email template seeding non-destructive.
# Run SERIALLY: pytest -n 0 (live-mode class flips settings.hubtel temporarily and restores it).
import copy
import os
import time
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ENV = {}
with open("/app/backend/.env") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            ENV[k] = v.strip('"')
mdb = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]

ADMIN = {"email": "admin@eghanavisa.com", "password": "Admin@2026"}
TEST_EMAIL = "delivered@resend.dev"
CREATED = []


@pytest.fixture(scope="module")
def H():
    r = requests.post(f"{BASE_URL}/api/admin/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.skip("login failed")
    tok = r.json()["token"]
    yield {"Authorization": f"Bearer {tok}"}
    for trk in CREATED:
        d = requests.delete(f"{BASE_URL}/api/admin/applications/{trk}", headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        print("cleanup", trk, d.status_code)


def _create(**extra):
    p = {
        "visa_code": "tourist_evisa", "passport_country": "France", "passport_number": "TEST12345",
        "passport_type": "Ordinary", "passport_expiry": "2030-01-01", "travelling_from": "France",
        "arrival_date": "2027-02-01", "departure_date": "2027-02-15", "full_name": "TEST_Iter16 User",
        "email": TEST_EMAIL, "phone": "+33600000000", "profession": "Engineer", "processing": "regular", "lang": "en",
    }
    p.update(extra)
    r = requests.post(f"{BASE_URL}/api/applications", json=p, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    CREATED.append(d["tracking_no"])
    return d


def _status(trk):
    return requests.get(f"{BASE_URL}/api/payments/status/{trk}", timeout=30).json()


def _forged(trk, status="Success"):
    code = "0000" if status == "Success" else "2001"
    return {"ResponseCode": code, "Status": status, "Data": {"ClientReference": trk, "Status": status, "CheckoutId": "FORGED-X"}}


# ---- Sandbox regression + FIX 2 (no downgrade) ----
class TestSandbox:
    def test_sandbox_checkout_confirm_marks_paid(self, H):
        assert mdb.settings.find_one({"id": "singleton"})["hubtel"]["sandbox"] is True
        trk = _create()["tracking_no"]
        init = requests.post(f"{BASE_URL}/api/payments/initiate", json={"tracking_no": trk}, timeout=30)
        assert init.status_code == 200 and init.json().get("transaction_id")
        c = requests.post(f"{BASE_URL}/api/payments/confirm", json={"tracking_no": trk, "success": True}, timeout=30)
        assert c.status_code == 200 and c.json()["ok"] is True
        s = _status(trk)
        assert s["payment_status"] == "paid" and s["status"] == "submitted"
        time.sleep(2)
        logs = list(mdb.email_log.find({"$or": [{"context.tracking": trk}, {"subject": {"$regex": trk}}]}, {"_id": 0, "template_name": 1}))
        tpls = [l.get("template_name") for l in logs]
        assert "submitted" in tpls and "admin_payment_success" in tpls, tpls

    def test_sandbox_success_callback_marks_paid(self, H):
        trk = _create()["tracking_no"]
        r = requests.post(f"{BASE_URL}/api/webhooks/hubtel", json=_forged(trk), timeout=30)
        assert r.status_code == 200
        assert _status(trk)["payment_status"] == "paid"

    def test_failed_callback_does_not_downgrade_paid(self, H):
        trk = _create()["tracking_no"]
        requests.post(f"{BASE_URL}/api/payments/confirm", json={"tracking_no": trk, "success": True}, timeout=30)
        assert _status(trk)["payment_status"] == "paid"
        for st in ("Failed", "Cancelled"):
            requests.post(f"{BASE_URL}/api/webhooks/hubtel", json=_forged(trk, st), timeout=30)
        s = _status(trk)
        assert s["payment_status"] == "paid" and s["status"] == "submitted", s
        assert requests.get(f"{BASE_URL}/api/track/{trk}", timeout=30).status_code == 200

    def test_confirm_false_does_not_downgrade_paid(self, H):
        """Observation from iter15: /payments/confirm success=false on a paid app."""
        trk = _create()["tracking_no"]
        requests.post(f"{BASE_URL}/api/payments/confirm", json={"tracking_no": trk, "success": True}, timeout=30)
        requests.post(f"{BASE_URL}/api/payments/confirm", json={"tracking_no": trk, "success": False}, timeout=30)
        assert _status(trk)["payment_status"] == "paid", "sandbox confirm success=false downgraded a paid app"

    def test_failed_callback_on_pending_marks_failed(self, H):
        trk = _create()["tracking_no"]
        requests.post(f"{BASE_URL}/api/webhooks/hubtel", json=_forged(trk, "Failed"), timeout=30)
        assert _status(trk)["payment_status"] == "failed"

    def test_verify_payment_rejected_in_sandbox(self, H):
        trk = _create()["tracking_no"]
        r = requests.post(f"{BASE_URL}/api/admin/applications/{trk}/verify-payment", headers=H, timeout=30)
        assert r.status_code == 400 and "sandbox" in r.text.lower()

    def test_verification_endpoints_require_auth(self):
        assert requests.get(f"{BASE_URL}/api/admin/payment-verifications", timeout=30).status_code in (401, 403)
        assert requests.post(f"{BASE_URL}/api/admin/applications/GH-X/verify-payment", timeout=30).status_code in (401, 403)


# ---- FIX 1: LIVE mode forged callback must NOT mark paid ----
class TestLiveForgedCallback:
    def test_live_forged_callback_not_paid(self, H):
        trk = _create()["tracking_no"]
        # initiate in sandbox -> sets payment_method=hubtel, amount_charged
        assert requests.post(f"{BASE_URL}/api/payments/initiate", json={"tracking_no": trk}, timeout=30).status_code == 200
        doc = mdb.applications.find_one({"tracking_no": trk})
        assert doc["payment_method"] == "hubtel" and doc["amount_charged"] > 0 and doc["payment_status"] != "paid"
        orig = copy.deepcopy(mdb.settings.find_one({"id": "singleton"})["hubtel"])
        live = dict(orig, sandbox=False, api_id="TEST_fake_id", api_key="TEST_fake_key", merchant_account_id="1234567")
        mdb.settings.update_one({"id": "singleton"}, {"$set": {"hubtel": live}})
        try:
            r = requests.post(f"{BASE_URL}/api/webhooks/hubtel", json=_forged(trk), timeout=30)
            assert r.status_code == 200
            # live: /payments/confirm must be rejected
            assert requests.post(f"{BASE_URL}/api/payments/confirm", json={"tracking_no": trk, "success": True}, timeout=30).status_code == 403
            time.sleep(25)
            d = mdb.applications.find_one({"tracking_no": trk}, {"_id": 0})
            print("verification:", d.get("payment_verification"))
            assert d["payment_status"] != "paid", "LIVE forged callback marked PAID"
            assert d["payment_status"] == "pending", d["payment_status"]
            ver = d.get("payment_verification") or {}
            assert ver.get("state") in ("error", "unpaid"), ver
            # status poll also must not mark paid
            assert _status(trk)["payment_status"] != "paid"
            # admin list
            lst = requests.get(f"{BASE_URL}/api/admin/payment-verifications", headers=H, timeout=30)
            assert lst.status_code == 200
            row = [x for x in lst.json() if x["tracking_no"] == trk]
            assert row and row[0]["payment_verification"]["state"] in ("error", "unpaid") and "_id" not in row[0]
            # manual verify
            v = requests.post(f"{BASE_URL}/api/admin/applications/{trk}/verify-payment", headers=H, timeout=60)
            assert v.status_code == 200, v.text
            vj = v.json()
            print("manual verify:", vj)
            assert vj["state"] in ("error", "unpaid") and vj["payment_status"] != "paid"
            assert vj["payment_verification"]["attempts"] >= 2
            # 404 on unknown
            assert requests.post(f"{BASE_URL}/api/admin/applications/GH-0000-000000/verify-payment", headers=H, timeout=30).status_code == 404
            # failed callback in live with unverifiable status: must not mark paid either
            requests.post(f"{BASE_URL}/api/webhooks/hubtel", json=_forged(trk, "Failed"), timeout=30)
            time.sleep(8)
            assert mdb.applications.find_one({"tracking_no": trk})["payment_status"] != "paid"
        finally:
            mdb.settings.update_one({"id": "singleton"}, {"$set": {"hubtel": orig}})
        assert mdb.settings.find_one({"id": "singleton"})["hubtel"] == orig


# ---- FIX 6: email templates seeding non-destructive ----
class TestTemplatesSeed:
    def test_templates_unchanged_after_restart(self, H):
        tpls = requests.get(f"{BASE_URL}/api/admin/email-templates", headers=H, timeout=30).json()
        before = len(tpls)
        t = next(x for x in tpls if x["template_name"] == "done" and x["lang"] == "en") if any(
            x["template_name"] == "done" and x["lang"] == "en" for x in tpls) else tpls[0]
        orig_subject, orig_html = t["subject"], t["html"]
        edited = orig_subject + " TEST_EDIT"
        assert requests.post(f"{BASE_URL}/api/admin/email-templates", headers=H, json={
            "template_name": t["template_name"], "lang": t["lang"], "subject": edited, "html": orig_html}, timeout=30).status_code == 200
        try:
            os.system("sudo supervisorctl restart backend >/dev/null 2>&1")
            for _ in range(40):
                time.sleep(2)
                try:
                    if requests.get(f"{BASE_URL}/api/config", timeout=10).status_code == 200:
                        break
                except Exception:
                    pass
            H2 = {"Authorization": requests.post(f"{BASE_URL}/api/admin/login", json=ADMIN, timeout=30).json()["token"]}
            H2 = {"Authorization": f"Bearer {H2['Authorization']}"}
            after = requests.get(f"{BASE_URL}/api/admin/email-templates", headers=H2, timeout=30).json()
            assert len(after) == before
            got = next(x for x in after if x["template_name"] == t["template_name"] and x["lang"] == t["lang"])
            assert got["subject"] == edited
        finally:
            requests.post(f"{BASE_URL}/api/admin/email-templates", headers=H, json={
                "template_name": t["template_name"], "lang": t["lang"], "subject": orig_subject, "html": orig_html}, timeout=30)
