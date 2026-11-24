# NOWPayments hardening: a 'finished' notification only marks an application paid after the
# NOWPayments API confirms reference, amount, currency/network and final status. In-process test
# with the NOWPayments API mocked (no real crypto payment involved).
import asyncio
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
import server  # noqa: E402

LOOP = asyncio.new_event_loop()


def run(coro):
    return LOOP.run_until_complete(coro)


def _seed(sandbox):
    trk = f"TEST-NP-{uuid.uuid4().hex[:8].upper()}"
    pid = f"TESTNP{uuid.uuid4().hex[:10]}"
    run(server.db.applications.insert_one({
        "tracking_no": trk, "full_name": "TEST_NP User", "email": "delivered@resend.dev", "payment_status": "pending",
        "status": "pending_payment", "processing": "regular", "visa_name": "Tourist eVisa", "amount_usd": 350.0, "lang": "en",
        "created_at": server.now_iso()}))
    run(server.db.crypto_payments.insert_one({
        "payment_id": pid, "tracking_no": trk, "network": "trc20", "pay_currency": "usdttrc20", "pay_amount": 350.0,
        "price_amount_usd": 350.0, "payment_status": "waiting", "sandbox": sandbox, "simulated": False,
        "created_at": server.now_iso(), "ipn_payloads": []}))
    return trk, pid


def _remote(pid, trk, **over):
    r = {"payment_id": pid, "payment_status": "finished", "order_id": trk, "pay_currency": "usdttrc20",
         "pay_amount": 350.0, "actually_paid": 350.0, "price_amount": 350.0, "price_currency": "usd"}
    r.update(over)
    return r


@pytest.fixture
def env(monkeypatch):
    sandbox = bool((run(server.get_settings()).get("nowpayments") or {}).get("sandbox", True))
    created = []

    def make(remote_over=None, raise_err=False):
        trk, pid = _seed(sandbox)
        created.append(trk)

        def fake(cfg, payment_id):
            if raise_err:
                raise RuntimeError("network down")
            return _remote(pid, trk, **(remote_over or {}))
        monkeypatch.setattr(server.nowp, "get_payment", fake)
        return trk, pid
    yield make
    for trk in created:
        run(server.db.applications.delete_one({"tracking_no": trk}))
        run(server.db.crypto_payments.delete_one({"tracking_no": trk}))


def _app(trk):
    return run(server.db.applications.find_one({"tracking_no": trk}, {"_id": 0}))


def test_verified_payment_marks_paid(env):
    trk, pid = env()
    run(server._apply_crypto_status_update(pid, "finished", {"payment_id": pid}, ipn=True))
    a = _app(trk)
    assert a["payment_status"] == "paid" and a["payment_verification"]["state"] == "verified"


@pytest.mark.parametrize("over,reason", [
    ({"actually_paid": 100.0}, "amount_received"),
    ({"order_id": "GH-OTHER"}, "order_id"),
    ({"pay_currency": "usdtbsc"}, "currency_network"),
    ({"payment_status": "partially_paid"}, "final_status"),
    ({"price_amount": 10.0}, "price_usd"),
])
def test_mismatch_never_marks_paid(env, over, reason):
    trk, pid = env(over)
    run(server._apply_crypto_status_update(pid, "finished", {"payment_id": pid}, ipn=True))
    a = _app(trk)
    assert a["payment_status"] != "paid"
    assert a["payment_verification"]["state"] == "rejected" and reason in a["payment_verification"]["reasons"]


def test_api_error_keeps_pending(env):
    trk, pid = env(raise_err=True)
    run(server._apply_crypto_status_update(pid, "finished", {"payment_id": pid}, ipn=True))
    assert _app(trk)["payment_status"] != "paid"


def test_double_notification_single_validation(env):
    trk, pid = env()
    run(server._apply_crypto_status_update(pid, "finished", {"payment_id": pid}, ipn=True))
    paid_at = _app(trk)["paid_at"]
    run(server._apply_crypto_status_update(pid, "finished", {"payment_id": pid}, ipn=True))
    assert _app(trk)["paid_at"] == paid_at
