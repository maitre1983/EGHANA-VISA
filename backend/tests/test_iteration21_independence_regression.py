# Iteration 21: independence-notice deployment retry - read-only admin regression (5 lots + 4 admin features) and email-log checks.
# Does NOT change settings / SMS / prices. Apps created by the UI flow are passed via env ITER21_TRACKINGS (comma-separated).
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
TRACKINGS = [t for t in os.environ.get("ITER21_TRACKINGS", "").split(",") if t]


@pytest.fixture(scope="module")
def H():
    r = requests.post(f"{API}/admin/login", json={"email": "admin@eghanavisa.com", "password": "Admin@2026"}, timeout=30)
    if r.status_code != 200:
        pytest.skip("admin login failed")
    return {"Authorization": f"Bearer {r.json()['token']}"}


# Lot 1: dashboard search, date filters, pagination
def test_dashboard_search_dates_pagination(H):
    r = requests.get(f"{API}/admin/applications", headers=H, params={"page": 1, "page_size": 5}, timeout=30)
    assert r.status_code == 200
    d = r.json()
    items = d["items"] if isinstance(d, dict) else d
    assert len(items) <= 5
    r2 = requests.get(f"{API}/admin/applications", headers=H, params={"date_from": "2020-01-01", "date_to": "2099-12-31"}, timeout=30)
    assert r2.status_code == 200
    r3 = requests.get(f"{API}/admin/applications", headers=H, params={"search": "ZZZ_NO_MATCH_XYZ"}, timeout=30)
    assert r3.status_code == 200
    d3 = r3.json()
    assert len(d3["items"] if isinstance(d3, dict) else d3) == 0


# Lot 2 + 3: unified payments history, CSV + XLSX export
def test_transactions_and_exports(H):
    r = requests.get(f"{API}/admin/transactions", headers=H, timeout=30)
    assert r.status_code == 200
    c = requests.get(f"{API}/admin/transactions.csv", headers=H, timeout=60)
    assert c.status_code == 200 and "csv" in c.headers.get("content-type", "")
    x = requests.get(f"{API}/admin/transactions.xlsx", headers=H, timeout=60)
    assert x.status_code == 200 and x.content[:2] == b"PK"


# Admin features: tickets, monitoring, activity log, settings (SMS disabled)
@pytest.mark.parametrize("path", ["support-tickets", "audit-log", "health", "crypto-payments", "sms-log", "payment-verifications", "kpis"])
def test_admin_read_endpoints(H, path):
    r = requests.get(f"{API}/admin/{path}", headers=H, timeout=30)
    assert r.status_code == 200, r.text[:200]


def test_monitoring_check_now(H):
    r = requests.post(f"{API}/admin/health/check", headers=H, timeout=90)
    assert r.status_code == 200


def test_sms_still_disabled(H):
    s = requests.get(f"{API}/admin/settings", headers=H, timeout=30).json()
    assert s["sms"]["enabled"] is False


# Payment event emails: customer + admin emails logged for the UI-created paid app
@pytest.mark.skipif(not TRACKINGS, reason="no UI trackings provided")
def test_email_log_for_ui_apps(H):
    log = requests.get(f"{API}/admin/email-log", headers=H, params={"limit": 500}, timeout=30).json()
    entries = log if isinstance(log, list) else log.get("items", [])
    trk = TRACKINGS[0]  # hubtel paid app
    mine = [e for e in entries if trk in (e.get("subject") or "") or trk in (e.get("html") or "")]
    names = {e.get("template_name") for e in mine}
    print(trk, sorted(names), {e.get("recipient") for e in mine})
    assert any(n and n.startswith("admin") for n in names), names
    assert any(n and not n.startswith("admin") for n in names), names
