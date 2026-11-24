# PRODUCTION security guards: requests arriving on a non-preview host (e.g. eghanavisa.com)
# must never be able to mark an application paid through sandbox / simulated flows,
# even when the admin settings are left in sandbox mode.
import os
import sys
import time
import pytest
import requests
from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(__file__))
from test_iteration15_final_regression import _create  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
LOCAL = "http://localhost:8001"
PROD = {"Host": "eghanavisa.com"}


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    start = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    yield
    env = dict(line.strip().split("=", 1) for line in open("/app/backend/.env") if "=" in line)
    db = MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]
    db.applications.delete_many({"full_name": {"$regex": "^TEST_"}, "created_at": {"$gte": start}})


def _status(trk):
    return requests.get(f"{BASE_URL}/api/payments/status/{trk}", timeout=30).json()["payment_status"]


def test_confirm_endpoint_refused_on_production_host():
    trk = _create()["tracking_no"]
    r = requests.post(f"{LOCAL}/api/payments/confirm", json={"tracking_no": trk, "success": True}, headers=PROD, timeout=30)
    assert r.status_code == 403
    assert _status(trk) != "paid"


def test_sandbox_checkout_suspended_on_production_host():
    trk = _create()["tracking_no"]
    r = requests.post(f"{LOCAL}/api/payments/initiate", json={"tracking_no": trk}, headers=PROD, timeout=30)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "payments_suspended", r.text


def test_forged_hubtel_callback_never_marks_paid_on_production_host():
    trk = _create()["tracking_no"]
    body = {"ResponseCode": "0000", "Status": "Success", "Data": {"ClientReference": trk, "Status": "Success", "CheckoutId": "FORGED"}}
    assert requests.post(f"{LOCAL}/api/webhooks/hubtel", json=body, headers=PROD, timeout=30).status_code == 200
    time.sleep(3)
    assert _status(trk) != "paid"


def test_crypto_simulation_refused_on_production_host():
    r = requests.post(f"{LOCAL}/api/payments/crypto/simulate-finish/NP-SIM-ANY", json={"success": True}, headers=PROD, timeout=30)
    assert r.status_code == 403


def test_unsigned_nowpayments_ipn_rejected():
    r = requests.post(f"{LOCAL}/api/webhooks/nowpayments", json={"payment_id": "X", "payment_status": "finished"}, headers=PROD, timeout=30)
    assert r.status_code == 401


def test_preview_sandbox_flow_still_works():
    trk = _create()["tracking_no"]
    assert requests.post(f"{BASE_URL}/api/payments/initiate", json={"tracking_no": trk}, timeout=30).status_code == 200
    assert requests.post(f"{BASE_URL}/api/payments/confirm", json={"tracking_no": trk, "success": True}, timeout=30).status_code == 200
    assert _status(trk) == "paid"
