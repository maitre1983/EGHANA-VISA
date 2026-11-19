"""NowPayments integration — USDT TRC20 & BEP20 crypto payments.

Keys are stored in the settings collection and never hardcoded. Supports
sandbox and production toggle. Signature verification for IPN webhooks uses
HMAC-SHA512 over the JSON body sorted by keys, per NowPayments spec.
"""
import os
import hmac
import json
import hashlib
import logging
import requests

logger = logging.getLogger(__name__)

PROD_BASE = "https://api.nowpayments.io/v1"
SANDBOX_BASE = "https://api-sandbox.nowpayments.io/v1"

CURRENCY_MAP = {
    "trc20": "usdttrc20",
    "bep20": "usdtbsc",
}
NETWORK_LABEL = {
    "trc20": "USDT · TRON (TRC20)",
    "bep20": "USDT · Binance Smart Chain (BEP20)",
}


def is_configured(config: dict) -> bool:
    """Both API key and IPN secret must be set (for the current mode) to enable crypto payments."""
    sandbox = bool(config.get("sandbox", True))
    if sandbox:
        return bool((config.get("sandbox_api_key") or "").strip()) and bool((config.get("sandbox_ipn_secret") or "").strip())
    return bool((config.get("api_key") or "").strip()) and bool((config.get("ipn_secret") or "").strip())


def _base_url(config: dict) -> str:
    return SANDBOX_BASE if config.get("sandbox", True) else PROD_BASE


def _api_key(config: dict) -> str:
    return (config.get("sandbox_api_key") if config.get("sandbox", True) else config.get("api_key")) or ""


def _ipn_secret(config: dict) -> str:
    return (config.get("sandbox_ipn_secret") if config.get("sandbox", True) else config.get("ipn_secret")) or ""


def _headers(config: dict) -> dict:
    return {"x-api-key": _api_key(config), "Content-Type": "application/json"}


def _request(method: str, url: str, config: dict, **kwargs):
    resp = requests.request(method, url, headers=_headers(config), timeout=15, **kwargs)
    resp.raise_for_status()
    return resp.json()


# ────── public helpers ──────

def get_status(config: dict) -> dict:
    return _request("GET", f"{_base_url(config)}/status", config)


def get_currencies(config: dict) -> list[str]:
    data = _request("GET", f"{_base_url(config)}/currencies", config)
    return data.get("currencies", [])


def get_min_amount(config: dict, pay_currency: str) -> float:
    data = _request(
        "GET",
        f"{_base_url(config)}/min-amount",
        config,
        params={"currency_from": "usd", "currency_to": pay_currency},
    )
    return float(data.get("min_amount", 0) or 0)


def create_payment(
    config: dict,
    price_amount: float,
    pay_currency: str,
    order_id: str,
    ipn_callback_url: str,
) -> dict:
    payload = {
        "price_amount": round(float(price_amount), 2),
        "price_currency": "usd",
        "pay_currency": pay_currency,
        "order_id": order_id,
        "ipn_callback_url": ipn_callback_url,
    }
    return _request(
        "POST",
        f"{_base_url(config)}/payment",
        config,
        json=payload,
    )


def get_payment(config: dict, payment_id: str) -> dict:
    return _request("GET", f"{_base_url(config)}/payment/{payment_id}", config)


# ────── IPN signature verification ──────

def verify_ipn_signature(raw_body: bytes, signature_header: str, ipn_secret: str) -> bool:
    """HMAC-SHA512 over the JSON body sorted by keys (canonical), lowercase hex compare."""
    if not signature_header or not ipn_secret:
        return False
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return False
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    expected = hmac.new(
        ipn_secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha512,
    ).hexdigest().lower()
    received = signature_header.strip().lower()
    return hmac.compare_digest(expected, received)


# ────── Status mapping ──────

NOWPAYMENTS_STATUS_MAP = {
    "waiting": "pending",
    "confirming": "pending",
    "confirmed": "processing",
    "sending": "processing",
    "finished": "paid",
    "partially_paid": "partial",
    "failed": "failed",
    "refunded": "failed",
    "expired": "failed",
}


def map_status(np_status: str) -> str:
    return NOWPAYMENTS_STATUS_MAP.get(np_status, "pending")
