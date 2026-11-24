# Iteration 15 — pre-production final regression: application -> payment (Hubtel sandbox + NOWPayments sim)
# -> emails -> track -> admin ops -> exports -> payment-event idempotency -> chat -> new admin features (read-only SMS)
import io
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

ADMIN = {"email": "admin@eghanavisa.com", "password": "Admin@2026"}
TEST_EMAIL = "delivered@resend.dev"  # Resend sink address - never reaches a real person
CREATED = []


@pytest.fixture(scope="module")
def H():
    r = requests.post(f"{BASE_URL}/api/admin/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.skip("login failed")
    tok = r.json().get("token") or r.json().get("access_token")
    yield {"Authorization": f"Bearer {tok}"}
    for trk in CREATED:
        d = requests.delete(f"{BASE_URL}/api/admin/applications/{trk}", headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        print("cleanup", trk, d.status_code)


def _payload(visa="tourist_evisa", processing="regular", **extra):
    p = {
        "visa_code": visa, "passport_country": "France", "passport_number": "TEST12345",
        "passport_type": "Ordinary", "passport_expiry": "2030-01-01", "travelling_from": "France",
        "arrival_date": "2027-02-01", "departure_date": "2027-02-15", "full_name": "TEST_Regression User",
        "email": TEST_EMAIL, "phone": "+33600000000", "profession": "Engineer", "processing": processing, "lang": "en",
    }
    p.update(extra)
    return p


def _create(**kw):
    r = requests.post(f"{BASE_URL}/api/applications", json=_payload(**kw), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    CREATED.append(d["tracking_no"])
    return d


def _emails(H, trk):
    r = requests.get(f"{BASE_URL}/api/admin/email-log", headers=H, params={"limit": 500}, timeout=30)
    assert r.status_code == 200
    rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    return [e for e in rows if trk in (e.get("subject", "") + e.get("html", "") + str(e.get("context", "")))]


# ---- Application form ----
class TestApplications:
    def test_processing_tiers_totals(self, H):
        a = _create(processing="regular"); b = _create(processing="priority"); c = _create(processing="express")
        assert a["amount_usd"] == 350.0 and b["amount_usd"] == 375.0 and c["amount_usd"] == 400.0
        assert a["tracking_no"].startswith("GH-") and a["status"] == "pending_payment" and a["submitted_at"]

    def test_business_fields_required(self, H):
        r = requests.post(f"{BASE_URL}/api/applications", json=_payload(visa="business_evisa"), timeout=30)
        assert r.status_code == 400 and "business" in r.text.lower()
        d = _create(visa="business_evisa", company_name="TEST_Co", host_company="TEST_Host",
                    business_registration="REG1", purpose_of_visit="Meeting")
        assert d["amount_usd"] == 750.0 and d["company_name"] == "TEST_Co"

    def test_invalid_processing(self):
        r = requests.post(f"{BASE_URL}/api/applications", json=_payload(processing="turbo"), timeout=30)
        assert r.status_code == 400

    def test_document_upload(self, H):
        d = _create()
        png = bytes.fromhex("89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4890000000D4944415478DA63F8CFC0F01F0005000201E2D2D6A70000000049454E44AE426082")
        r = requests.post(f"{BASE_URL}/api/applications/{d['tracking_no']}/documents",
                          data={"doc_type": "face_photo"}, files={"file": ("face.png", png, "image/png")}, timeout=60)
        assert r.status_code == 200, r.text
        g = requests.get(f"{BASE_URL}/api/admin/applications/{d['tracking_no']}", headers=H, timeout=30).json()
        assert "face_photo" in (g.get("documents") or {})
        bad = requests.post(f"{BASE_URL}/api/applications/{d['tracking_no']}/documents",
                            data={"doc_type": "bogus"}, files={"file": ("a.png", png, "image/png")}, timeout=30)
        assert bad.status_code == 400


# ---- Hubtel sandbox + emails + track + admin status ----
class TestHubtelFlow:
    def test_full_flow(self, H):
        d = _create(processing="express"); trk = d["tracking_no"]
        assert requests.get(f"{BASE_URL}/api/track/{trk}", timeout=30).status_code == 404  # unpaid hidden
        init = requests.post(f"{BASE_URL}/api/payments/initiate", json={"tracking_no": trk}, timeout=30)
        assert init.status_code == 200, init.text
        assert init.json().get("transaction_id")
        c = requests.post(f"{BASE_URL}/api/payments/confirm", json={"tracking_no": trk, "success": True}, timeout=30)
        assert c.status_code == 200 and c.json()["ok"] is True
        s = requests.get(f"{BASE_URL}/api/payments/status/{trk}", timeout=30).json()
        assert s["payment_status"] == "paid" and s["status"] == "submitted"
        t = requests.get(f"{BASE_URL}/api/track/{trk}", timeout=30)
        assert t.status_code == 200 and t.json()["status"] == "submitted"
        time.sleep(2)
        tpls = [e["template_name"] for e in _emails(H, trk)]
        assert "submitted" in tpls and "admin_payment_success" in tpls, tpls
        # second confirm is idempotent (no duplicate submitted email)
        requests.post(f"{BASE_URL}/api/payments/confirm", json={"tracking_no": trk, "success": True}, timeout=30)
        time.sleep(1)
        assert [e["template_name"] for e in _emails(H, trk)].count("submitted") == 1
        assert requests.post(f"{BASE_URL}/api/payments/initiate", json={"tracking_no": trk}, timeout=30).status_code == 400
        # admin status changes
        for st in ("in_progress", "done"):
            r = requests.post(f"{BASE_URL}/api/admin/applications/{trk}/status", json={"status": st}, headers=H, timeout=30)
            assert r.status_code == 200
        time.sleep(2)
        tpls = [e["template_name"] for e in _emails(H, trk)]
        assert "in_progress" in tpls and "done" in tpls, tpls
        assert requests.get(f"{BASE_URL}/api/track/{trk}", timeout=30).json()["status"] == "done"
        TestHubtelFlow.trk = trk

    def test_admin_list_search_dates(self, H):
        trk = TestHubtelFlow.trk
        r = requests.get(f"{BASE_URL}/api/admin/applications", headers=H, params={"search": trk}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        items = body if isinstance(body, list) else body.get("items", body.get("applications", []))
        assert any(a["tracking_no"] == trk for a in items)
        today = time.strftime("%Y-%m-%d", time.gmtime())
        r2 = requests.get(f"{BASE_URL}/api/admin/applications", headers=H,
                          params={"from_date": today, "to_date": today, "search": trk}, timeout=30).json()
        items2 = r2 if isinstance(r2, list) else r2.get("items", r2.get("applications", []))
        assert any(a["tracking_no"] == trk for a in items2)
        r3 = requests.get(f"{BASE_URL}/api/admin/applications", headers=H,
                          params={"from_date": "2020-01-01", "to_date": "2020-01-02", "search": trk}, timeout=30).json()
        items3 = r3 if isinstance(r3, list) else r3.get("items", r3.get("applications", []))
        assert not any(a["tracking_no"] == trk for a in items3)

    def test_transactions_and_exports(self, H):
        trk = TestHubtelFlow.trk
        r = requests.get(f"{BASE_URL}/api/admin/transactions", headers=H, params={"search": trk}, timeout=30)
        assert r.status_code == 200
        txs = [t for t in r.json()["transactions"] if t["tracking_no"] == trk]
        assert txs and txs[0]["status"] == "paid" and txs[0]["amount"] == 400.0
        det = requests.get(f"{BASE_URL}/api/admin/transactions/{txs[0]['id']}", headers=H, timeout=30)
        assert det.status_code == 200
        csv_r = requests.get(f"{BASE_URL}/api/admin/transactions.csv", headers=H, timeout=60)
        assert csv_r.status_code == 200 and trk in csv_r.text
        x = requests.get(f"{BASE_URL}/api/admin/transactions.xlsx", headers=H, timeout=60)
        assert x.status_code == 200 and x.content[:2] == b"PK"
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(x.content))
        vals = [str(c.value) for row in wb.active.iter_rows() for c in row]
        assert trk in vals


# ---- NOWPayments simulation ----
class TestCrypto:
    def test_crypto_sim(self, H):
        d = _create(); trk = d["tracking_no"]
        i = requests.post(f"{BASE_URL}/api/payments/crypto/initiate", json={"tracking_no": trk, "network": "trc20"}, timeout=30)
        assert i.status_code == 200, i.text
        j = i.json(); assert j["pay_amount"] > 0
        if not j["simulated"]:
            pytest.skip("NOWPayments LIVE keys configured in this env - simulate-finish unavailable (real invoice created)")
        f = requests.post(f"{BASE_URL}/api/payments/crypto/simulate-finish/{j['payment_id']}", json={"success": True}, timeout=30)
        assert f.status_code == 200
        st = requests.get(f"{BASE_URL}/api/payments/crypto/status/{j['payment_id']}", timeout=30).json()
        assert st["payment_status"] == "finished"
        assert requests.get(f"{BASE_URL}/api/payments/status/{trk}", timeout=30).json()["payment_status"] == "paid"
        assert requests.post(f"{BASE_URL}/api/payments/crypto/initiate", json={"tracking_no": trk, "network": "bep20"}, timeout=30).status_code == 400
        assert requests.post(f"{BASE_URL}/api/payments/crypto/initiate", json={"tracking_no": trk, "network": "btc"}, timeout=30).status_code == 400


# ---- Hubtel webhook: failure idempotency + security observations ----
class TestHubtelWebhook:
    def test_failed_twice_one_email(self, H):
        d = _create(); trk = d["tracking_no"]
        requests.post(f"{BASE_URL}/api/payments/initiate", json={"tracking_no": trk}, timeout=30)
        body = {"ResponseCode": "2001", "Status": "Failed", "Data": {"ClientReference": trk, "Status": "Failed", "CheckoutId": f"CHK-{trk}"}}
        for _ in range(2):
            assert requests.post(f"{BASE_URL}/api/webhooks/hubtel", json=body, timeout=30).status_code == 200
        time.sleep(2)
        tpls = [e["template_name"] for e in _emails(H, trk)]
        # one dispatch per admin recipient (same fan-out as admin_new_submission)
        assert tpls.count("admin_payment_failed") == tpls.count("admin_new_submission"), tpls
        assert requests.get(f"{BASE_URL}/api/payments/status/{trk}", timeout=30).json()["payment_status"] == "failed"

    def test_failed_callback_after_paid_must_not_downgrade(self, H):
        d = _create(); trk = d["tracking_no"]
        requests.post(f"{BASE_URL}/api/payments/confirm", json={"tracking_no": trk, "success": True}, timeout=30)
        body = {"Status": "Failed", "Data": {"ClientReference": trk, "Status": "Failed"}}
        requests.post(f"{BASE_URL}/api/webhooks/hubtel", json=body, timeout=30)
        s = requests.get(f"{BASE_URL}/api/payments/status/{trk}", timeout=30).json()
        assert s["payment_status"] == "paid", f"paid app downgraded to {s}"

    def test_sandbox_preview_callback_marks_paid(self, H):
        """SANDBOX + PREVIEW ONLY: an unsigned success callback is trusted by design so the mock checkout works.
        Production protection (non-preview host) is covered by test_payment_production_guards.py."""
        d = _create(); trk = d["tracking_no"]
        body = {"ResponseCode": "0000", "Status": "Success", "Data": {"ClientReference": trk, "Status": "Success", "CheckoutId": "FORGED"}}
        requests.post(f"{BASE_URL}/api/webhooks/hubtel", json=body, timeout=30)
        s = requests.get(f"{BASE_URL}/api/payments/status/{trk}", timeout=30).json()
        assert s["payment_status"] == "paid", s


# ---- Abena chat ----
class TestChat:
    def test_multi_turn(self):
        r = requests.post(f"{BASE_URL}/api/chat", json={"message": "What is the price of a tourist visa?"}, timeout=90)
        assert r.status_code == 200, r.text
        d = r.json(); sid = d["session_id"]; assert d.get("reply")
        r2 = requests.post(f"{BASE_URL}/api/chat", json={"message": "And how long does express take?", "session_id": sid}, timeout=90)
        assert r2.status_code == 200 and r2.json()["session_id"] == sid and r2.json().get("reply")


# ---- New admin features (read-only for SMS) ----
class TestAdminOps:
    def test_read_endpoints(self, H):
        for p in ("kpis", "support-tickets", "health", "audit-log", "sms-log", "settings", "crypto-payments"):
            r = requests.get(f"{BASE_URL}/api/admin/{p}", headers=H, timeout=30)
            assert r.status_code == 200, (p, r.status_code)
        s = requests.get(f"{BASE_URL}/api/admin/settings", headers=H, timeout=30).json()
        assert s["sms"]["enabled"] is False

    def test_health_check_now(self, H):
        r = requests.post(f"{BASE_URL}/api/admin/health/check", headers=H, timeout=60)
        assert r.status_code == 200

    def test_auth_required(self):
        for p in ("kpis", "transactions", "audit-log", "health", "email-log"):
            assert requests.get(f"{BASE_URL}/api/admin/{p}", timeout=30).status_code in (401, 403)
