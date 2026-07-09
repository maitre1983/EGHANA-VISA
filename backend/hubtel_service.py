"""Hubtel Online Checkout integration with SANDBOX simulation mode.

Configuration is read from the `settings` collection (Hubtel section). If any of
the required keys are missing, the service operates in SANDBOX mode and returns
a mock checkout URL. This is safe until real credentials are set.
"""
import os
import uuid
import logging
import requests

logger = logging.getLogger(__name__)

HUBTEL_CHECKOUT_URL = "https://payproxyapi.hubtel.com/items/initiate"


def _proxies_from(config: dict) -> dict | None:
    """Optional Fixie-style static outbound proxy."""
    proxy_url = (config.get("outbound_proxy_url") or "").strip()
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def is_sandbox(config: dict) -> bool:
    if config.get("sandbox", True):
        return True
    required = ("api_id", "api_key", "merchant_account_id")
    return not all((config.get(k) or "").strip() for k in required)


def initiate_checkout(config: dict, amount: float, description: str, tracking_no: str) -> dict:
    """Return {"checkout_url": str, "transaction_id": str, "sandbox": bool}."""
    tx_id = f"TX-{uuid.uuid4().hex[:10].upper()}"

    if is_sandbox(config):
        logger.info(f"Hubtel SANDBOX: simulated checkout for {tracking_no} amount={amount}")
        return {
            "checkout_url": f"/payment/sandbox?tx={tx_id}&tracking={tracking_no}",
            "transaction_id": tx_id,
            "sandbox": True,
        }

    payload = {
        "totalAmount": round(amount, 2),
        "description": description[:100],
        "callbackUrl": config.get("callback_url", ""),
        "returnUrl": config.get("return_url", ""),
        "merchantAccountNumber": config.get("merchant_account_id"),
        "cancellationUrl": config.get("cancellation_url") or config.get("return_url", ""),
        "clientReference": tracking_no,
        # Application-wide currency contract: prices are ALWAYS stored in USD.
        # Hubtel converts USD → GHS at checkout time (multi-currency merchant setup required).
        "currency": (config.get("currency") or "USD").upper(),
    }
    auth = (config["api_id"], config["api_key"])
    proxies = _proxies_from(config)
    try:
        resp = requests.post(
            HUBTEL_CHECKOUT_URL,
            json=payload,
            auth=auth,
            proxies=proxies,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        return {
            "checkout_url": data.get("checkoutUrl", ""),
            "transaction_id": data.get("checkoutId", tx_id),
            "sandbox": False,
        }
    except Exception as e:
        logger.error(f"Hubtel checkout failed: {e}")
        raise RuntimeError(f"Payment gateway error: {e}")
