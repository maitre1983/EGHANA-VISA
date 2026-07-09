"""Hubtel Online Checkout integration.

Configuration is fully driven by the admin settings collection. The admin
dashboard controls sandbox vs. production mode via the explicit `sandbox`
boolean — there is NO silent fallback to sandbox when credentials are
missing. When production mode is selected without the required credentials
the service surfaces a clear `HubtelNotConfiguredError` so the caller can
show a helpful message to admins/customers instead of quietly downgrading
real payments to a mock checkout.
"""
import uuid
import logging
import requests

logger = logging.getLogger(__name__)

HUBTEL_CHECKOUT_URL = "https://payproxyapi.hubtel.com/items/initiate"
REQUIRED_LIVE_FIELDS = ("api_id", "api_key", "merchant_account_id")


class HubtelNotConfiguredError(RuntimeError):
    """Raised when production mode is selected but credentials are missing."""

    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(
            "Hubtel is set to PRODUCTION but the following required fields are "
            "empty in Admin Settings → Hubtel API: " + ", ".join(missing) +
            ". Please fill them in (or switch Hubtel back to Sandbox) and save."
        )


def _proxies_from(config: dict) -> dict | None:
    """Optional Fixie-style static outbound proxy."""
    proxy_url = (config.get("outbound_proxy_url") or "").strip()
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def is_sandbox(config: dict) -> bool:
    """Strictly reflect the admin-configured mode. No implicit fallback."""
    return bool(config.get("sandbox", True))


def missing_live_fields(config: dict) -> list[str]:
    """List Hubtel credential fields that are empty. Only meaningful when
    admin has switched sandbox=false."""
    return [f for f in REQUIRED_LIVE_FIELDS if not str(config.get(f) or "").strip()]


def is_ready_for_live(config: dict) -> bool:
    """True when admin has selected production mode AND all required
    credentials are present. Used by the public /api/config endpoint so the
    frontend can show a clear 'not configured' warning if needed."""
    return not is_sandbox(config) and not missing_live_fields(config)


def initiate_checkout(config: dict, amount: float, description: str, tracking_no: str) -> dict:
    """Return {"checkout_url": str, "transaction_id": str, "sandbox": bool}.

    Raises HubtelNotConfiguredError when production mode is selected but any
    required credential field is empty."""
    tx_id = f"TX-{uuid.uuid4().hex[:10].upper()}"

    if is_sandbox(config):
        logger.info(f"Hubtel SANDBOX (admin-selected): simulated checkout for {tracking_no} amount={amount}")
        return {
            "checkout_url": f"/payment/sandbox?tx={tx_id}&tracking={tracking_no}",
            "transaction_id": tx_id,
            "sandbox": True,
        }

    # Production mode — validate credentials strictly, do NOT fall back to sandbox.
    missing = missing_live_fields(config)
    if missing:
        raise HubtelNotConfiguredError(missing)

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
