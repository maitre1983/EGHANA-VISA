"""Payment gateway health checks (Hubtel checkout, NowPayments, Hubtel SMS)."""
import asyncio
import time
from datetime import datetime, timezone

import httpx

import nowpayments_service as nowp
from sms_service import HUBTEL_SMS_BASE

HUBTEL_CHECKOUT_HOST = "https://payproxyapi.hubtel.com"


async def _probe(name: str, url: str, expect_json_ok: bool = False) -> dict:
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=5.0), follow_redirects=True) as c:
            r = await c.get(url)
        ms = int((time.perf_counter() - t0) * 1000)
        up = r.status_code < 500
        detail = f"HTTP {r.status_code}"
        if expect_json_ok and up:
            try:
                up = str(r.json().get("message", "")).upper() == "OK"
                detail += " · API OK" if up else " · API not OK"
            except Exception:
                up = False
                detail += " · invalid response"
        return {"gateway": name, "status": "up" if up else "down", "latency_ms": ms, "detail": detail}
    except Exception as e:
        ms = int((time.perf_counter() - t0) * 1000)
        return {"gateway": name, "status": "down", "latency_ms": ms, "detail": f"{type(e).__name__}: {str(e)[:150]}"}


async def run_checks(settings: dict) -> dict:
    np_cfg = settings.get("nowpayments", {}) or {}
    targets = [
        _probe("hubtel", HUBTEL_CHECKOUT_HOST),
        _probe("nowpayments", f"{nowp._base_url(np_cfg)}/status", expect_json_ok=True),
    ]
    sms_on = bool((settings.get("sms") or {}).get("enabled"))
    if sms_on:
        targets.append(_probe("hubtel_sms", HUBTEL_SMS_BASE))
    results = await asyncio.gather(*targets)
    hubtel_cfg = settings.get("hubtel", {}) or {}
    mode = {
        "hubtel": "sandbox" if hubtel_cfg.get("sandbox", True) else "live",
        "nowpayments": "sandbox" if np_cfg.get("sandbox", True) else "live",
        "hubtel_sms": "live",
    }
    for r in results:
        r["mode"] = mode.get(r["gateway"], "")
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "up" if all(r["status"] == "up" for r in results) else "degraded",
        "results": list(results),
    }
