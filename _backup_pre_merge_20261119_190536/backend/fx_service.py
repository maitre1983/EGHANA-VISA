"""USD → GHS exchange rate service.

- Rate is fetched at Hubtel checkout time only (base currency remains USD).
- Admin can pick between multiple free providers, or set a manual rate.
- Rates are cached in-memory for a configurable TTL (default 15 min) so we
  don't hammer the upstream API on every checkout.
- An optional `buffer_pct` lets the admin add a small safety margin to
  cover intraday FX drift between fetch and card settlement.
"""
from __future__ import annotations

import time
import logging
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Free providers (no API key). Each entry describes:
#   url: template with {base} placeholder
#   parse: callable(dict) -> float (GHS rate)
PROVIDERS = {
    "open_er_api": {
        "label": "open.er-api.com (free, no key)",
        "url": "https://open.er-api.com/v6/latest/USD",
        "parse": lambda d: float(d["rates"]["GHS"]),
    },
    "fawazahmed": {
        "label": "fawazahmed0/currency-api (free, no key)",
        "url": "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json",
        "parse": lambda d: float(d["usd"]["ghs"]),
    },
    "frankfurter": {
        "label": "frankfurter.app (ECB rates, free)",
        "url": "https://api.frankfurter.app/latest?from=USD&to=GHS",
        "parse": lambda d: float(d["rates"]["GHS"]),
    },
    "manual": {
        "label": "Manual (admin-entered rate)",
        "url": None,
        "parse": None,
    },
}

DEFAULT_PROVIDER = "open_er_api"
DEFAULT_TTL_SECONDS = 900       # 15 min cache
DEFAULT_BUFFER_PCT = 0.0        # no safety margin by default
FALLBACK_ORDER = ("open_er_api", "fawazahmed", "frankfurter")


class FxError(RuntimeError):
    pass


# ─────────────────── In-memory cache ───────────────────
_cache: dict[str, tuple[float, float, str]] = {}
# key = provider; value = (rate, fetched_epoch, source_url)


def _fetch_from_provider(provider_key: str) -> tuple[float, str]:
    """Return (rate, source_url). Raises FxError on failure."""
    entry = PROVIDERS.get(provider_key)
    if not entry or not entry["url"]:
        raise FxError(f"Provider '{provider_key}' cannot be fetched from network")
    try:
        r = requests.get(entry["url"], timeout=8)
        r.raise_for_status()
        rate = entry["parse"](r.json())
        if not rate or rate <= 0:
            raise FxError("Provider returned non-positive rate")
        return float(rate), entry["url"]
    except FxError:
        raise
    except Exception as e:
        raise FxError(f"{provider_key} error: {e}") from e


def get_rate(config: dict) -> dict:
    """Return the current USD → GHS rate as a dict:
        { rate, buffered_rate, provider, source_url, fetched_at, from_cache, buffer_pct }
    Never raises — falls back to configured manual rate if all providers fail."""
    cfg = config or {}
    provider = str(cfg.get("provider") or DEFAULT_PROVIDER).lower().strip()
    ttl = int(cfg.get("cache_seconds") or DEFAULT_TTL_SECONDS)
    buffer_pct = float(cfg.get("buffer_pct") or DEFAULT_BUFFER_PCT)
    manual_rate = float(cfg.get("manual_rate") or 0)

    # Manual mode short-circuits network calls
    if provider == "manual":
        if manual_rate <= 0:
            raise FxError("FX provider set to 'manual' but no manual_rate configured")
        rate = manual_rate
        return _build_result(rate, buffer_pct, "manual", "admin-configured", from_cache=False)

    # Serve from cache if fresh
    now = time.time()
    cached = _cache.get(provider)
    if cached and (now - cached[1]) < ttl:
        return _build_result(cached[0], buffer_pct, provider, cached[2], from_cache=True)

    # Try requested provider first, then documented fallbacks
    tried: list[str] = []
    last_err: Optional[Exception] = None
    for candidate in (provider, *[p for p in FALLBACK_ORDER if p != provider]):
        if candidate == "manual":
            continue
        tried.append(candidate)
        try:
            rate, url = _fetch_from_provider(candidate)
            _cache[candidate] = (rate, now, url)
            return _build_result(rate, buffer_pct, candidate, url, from_cache=False)
        except Exception as e:
            last_err = e
            logger.warning(f"FX provider {candidate} failed: {e}")

    # All network providers failed → fall back to manual rate if set
    if manual_rate > 0:
        return _build_result(manual_rate, buffer_pct, "manual (fallback)", "admin-configured", from_cache=False)

    raise FxError(f"All FX providers failed (tried: {', '.join(tried)}). Last error: {last_err}")


def _build_result(rate: float, buffer_pct: float, provider: str, source_url: str, from_cache: bool) -> dict:
    buffered = round(rate * (1 + buffer_pct / 100.0), 4)
    return {
        "rate": round(rate, 4),
        "buffered_rate": buffered,
        "buffer_pct": buffer_pct,
        "provider": provider,
        "source_url": source_url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "from_cache": from_cache,
    }


def convert_usd_to_ghs(amount_usd: float, config: dict) -> dict:
    """Convert a USD amount into GHS using the current rate. Returns dict with
    reconciliation-grade metadata that MUST be persisted on the payment record."""
    fx = get_rate(config)
    amount_ghs = round(float(amount_usd) * fx["buffered_rate"], 2)
    return {
        "amount_usd": round(float(amount_usd), 2),
        "amount_ghs": amount_ghs,
        "fx_rate": fx["rate"],
        "fx_rate_applied": fx["buffered_rate"],
        "fx_provider": fx["provider"],
        "fx_source_url": fx["source_url"],
        "fx_buffer_pct": fx["buffer_pct"],
        "fx_fetched_at": fx["fetched_at"],
        "fx_from_cache": fx["from_cache"],
    }


def clear_cache():
    _cache.clear()
