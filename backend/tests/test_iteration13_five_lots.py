# Iteration 13 — post-merge non-regression for 5 Lots (dashboard pagination, transactions, email tpl, indexes, xlsx)
import io
import os
import csv
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN = {"email": "admin@eghanavisa.com", "password": "Admin@2026"}


def _mongo():
    env = {}
    with open("/app/backend/.env") as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                env[k] = v.strip('"')
    return MongoClient(env["MONGO_URL"])[env["DB_NAME"]]


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/admin/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}"}


# --- Non-regression: auth / kpis / config / HEAD
class TestNonRegression:
    def test_login_returns_jwt(self):
        r = requests.post(f"{BASE_URL}/api/admin/login", json=ADMIN, timeout=30)
        assert r.status_code == 200
        tok = r.json().get("token") or r.json().get("access_token")
        assert isinstance(tok, str) and tok.count(".") == 2

    def test_login_bad_password(self):
        r = requests.post(f"{BASE_URL}/api/admin/login", json={"email": ADMIN["email"], "password": "nope"}, timeout=30)
        assert r.status_code in (400, 401)

    def test_kpis(self, H):
        r = requests.get(f"{BASE_URL}/api/admin/kpis", headers=H, timeout=30)
        assert r.status_code == 200
        d = r.json()
        print(d)
        assert d["revenue_usd"] == 700
        assert d["total"] == 2
        assert d["done"] == 1
        assert d["submitted"] == 1

    def test_config(self):
        r = requests.get(f"{BASE_URL}/api/config", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "whatsapp_public_number" in d
        assert "whatsapp_agent_name" in d
        assert "visa_types" in d and d["visa_types"]

    def test_head_config(self):
        r = requests.head(f"{BASE_URL}/api/config", timeout=30)
        assert r.status_code == 200
        assert len(r.content) == 0

    def test_admin_requires_auth(self):
        for p in ("/api/admin/transactions", "/api/admin/transactions.csv", "/api/admin/transactions.xlsx", "/api/admin/applications"):
            r = requests.get(f"{BASE_URL}{p}", timeout=30)
            assert r.status_code in (401, 403), p


# --- LOT 1: applications pagination & filters
class TestLot1Applications:
    def test_default_list(self, H):
        r = requests.get(f"{BASE_URL}/api/admin/applications", headers=H, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, list)
        tns = {a["tracking_no"] for a in d}
        assert {"GH-2026-318639", "GH-2026-204806"} <= tns
        assert all("_id" not in a for a in d)

    def test_pagination(self, H):
        r1 = requests.get(f"{BASE_URL}/api/admin/applications", headers=H, params={"page": 1, "page_size": 1}, timeout=30).json()
        r2 = requests.get(f"{BASE_URL}/api/admin/applications", headers=H, params={"page": 2, "page_size": 1}, timeout=30).json()
        assert len(r1) == 1 and len(r2) == 1
        assert r1[0]["tracking_no"] != r2[0]["tracking_no"]

    def test_page_size_cap(self, H):
        r = requests.get(f"{BASE_URL}/api/admin/applications", headers=H, params={"page_size": 1001}, timeout=30)
        assert r.status_code == 422
        r = requests.get(f"{BASE_URL}/api/admin/applications", headers=H, params={"page_size": 1000}, timeout=30)
        assert r.status_code == 200

    def test_search(self, H):
        r = requests.get(f"{BASE_URL}/api/admin/applications", headers=H, params={"search": "318639"}, timeout=30).json()
        assert [a["tracking_no"] for a in r] == ["GH-2026-318639"]
        r = requests.get(f"{BASE_URL}/api/admin/applications", headers=H, params={"search": "zz_nomatch_zz"}, timeout=30).json()
        assert r == []

    def test_date_filter(self, H):
        r = requests.get(f"{BASE_URL}/api/admin/applications", headers=H, params={"from_date": "2000-01-01", "to_date": "2099-12-31"}, timeout=30).json()
        assert len(r) >= 2
        r = requests.get(f"{BASE_URL}/api/admin/applications", headers=H, params={"from_date": "2099-01-01"}, timeout=30).json()
        assert r == []


# --- LOT 2/5: transactions list, detail, csv, xlsx
class TestLot2Transactions:
    def test_list_shape(self, H):
        r = requests.get(f"{BASE_URL}/api/admin/transactions", headers=H, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d["transactions"], list)
        s = d["summary"]
        assert "confirmed_revenue" in s and "status_counts" in s and "total_transactions" in s
        assert s["total_transactions"] == len(d["transactions"])
        print(s)

    def test_filters(self, H):
        d = requests.get(f"{BASE_URL}/api/admin/transactions", headers=H, params={"status": "paid"}, timeout=30).json()
        assert all(t["status"] == "paid" for t in d["transactions"])
        d = requests.get(f"{BASE_URL}/api/admin/transactions", headers=H, params={"provider": "hubtel"}, timeout=30).json()
        assert all(t["provider"] == "hubtel" for t in d["transactions"])
        d = requests.get(f"{BASE_URL}/api/admin/transactions", headers=H, params={"from_date": "2099-01-01"}, timeout=30).json()
        assert d["transactions"] == []

    def test_detail(self, H):
        d = requests.get(f"{BASE_URL}/api/admin/transactions", headers=H, timeout=30).json()
        if not d["transactions"]:
            pytest.skip("no transactions")
        tx = d["transactions"][0]
        r = requests.get(f"{BASE_URL}/api/admin/transactions/{tx['id']}", headers=H, timeout=30)
        assert r.status_code == 200
        dd = r.json()
        assert dd["transaction"]["id"] == tx["id"]
        assert "raw" in dd and "application" in dd

    def test_detail_404(self, H):
        r = requests.get(f"{BASE_URL}/api/admin/transactions/app:nope:nope", headers=H, timeout=30)
        assert r.status_code == 404

    def test_csv(self, H):
        r = requests.get(f"{BASE_URL}/api/admin/transactions.csv", headers=H, timeout=30)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers.get("content-disposition", "")
        rows = list(csv.reader(io.StringIO(r.text)))
        assert rows[0] == ["date", "provider", "provider_reference", "tracking_no", "customer_name", "customer_email",
                           "amount", "currency", "network", "status", "audit_only", "payment_method_label", "source"]

    def test_xlsx(self, H):
        from openpyxl import load_workbook
        r = requests.get(f"{BASE_URL}/api/admin/transactions.xlsx", headers=H, timeout=30)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        wb = load_workbook(io.BytesIO(r.content))
        assert wb.sheetnames == ["Transactions", "Summary"]
        assert wb["Transactions"].max_column == 13
        # Excel cross-sheet refs must use '!' not '.' (LibreOffice-only syntax)
        formulas = [c.value for row in wb["Summary"].iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("=")]
        print("formulas:", formulas)
        for f in formulas:
            assert "Transactions." not in f, f"Invalid Excel formula syntax: {f}"


# --- LOT 3: email templates
class TestLot3Templates:
    def test_templates(self, H):
        r = requests.get(f"{BASE_URL}/api/admin/email-templates", headers=H, timeout=30)
        assert r.status_code == 200
        d = r.json()
        items = d if isinstance(d, list) else d.get("templates", d.get("items", []))
        names = {t.get("template_name") for t in items}
        for n in ("admin_payment_failed", "admin_payment_expired", "admin_payment_refunded"):
            assert n in names, n


# --- LOT 4: indexes (direct DB read-only inspection)
class TestLot4Indexes:
    def test_indexes(self):
        db = _mongo()
        expect = {
            "applications": ["tracking_no_1", "email_1", "pay_status_created_1", "created_at_desc_1", "submitted_at_1"],
            "hubtel_callbacks": ["client_reference_1", "checkout_id_1", "created_at_desc_1"],
            "crypto_payments": ["payment_id_1", "tracking_no_1", "created_at_desc_1"],
            "payment_notifications_log": ["key_unique_1"],
            "email_log": ["created_at_desc_1"],
            "analytics_events": ["event_time_1", "path_1"],
            "admins": ["email_unique_1"],
        }
        for coll, names in expect.items():
            info = db[coll].index_information()
            for n in names:
                assert n in info, f"{coll}.{n} missing"
        assert db.payment_notifications_log.index_information()["key_unique_1"].get("unique") is True
