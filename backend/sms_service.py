"""Hubtel Programmable SMS — admin alerts. Config lives in settings.sms (Admin UI)."""
import re
import uuid
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

HUBTEL_SMS_BASE = "https://sms.hubtel.com"
SMS_EVENTS = ("new_submission", "payment_success", "ticket_escalated")

DEFAULT_SMS = {
    "enabled": False,
    "client_id": "",
    "client_secret": "",
    "sender_id": "",
    "admin_numbers": [],
    "events": {e: True for e in SMS_EVENTS},
}


def normalize_number(raw: str) -> str:
    """'+233 24 123 4567' / '0241234567' → '233241234567'."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 10:
        digits = "233" + digits[1:]
    return digits


def is_configured(cfg: dict) -> bool:
    return bool(
        (cfg.get("client_id") or "").strip()
        and (cfg.get("client_secret") or "").strip()
        and (cfg.get("sender_id") or "").strip()
        and cfg.get("admin_numbers")
    )


async def send_one(cfg: dict, to: str, content: str) -> dict:
    async with httpx.AsyncClient(base_url=HUBTEL_SMS_BASE, timeout=httpx.Timeout(10.0, connect=5.0)) as c:
        r = await c.post(
            "/v1/messages/send",
            auth=(cfg["client_id"].strip(), cfg["client_secret"].strip()),
            json={"From": cfg["sender_id"].strip(), "To": to, "Content": content},
        )
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text[:300]}
    ok = r.status_code < 400 and isinstance(data, dict) and data.get("status") in (0, "0")
    return {"ok": ok, "http_status": r.status_code, "response": data}


async def send_admin_sms(db, cfg: dict, event: str, content: str, force: bool = False) -> list:
    """Send `content` to every admin number; logs each attempt in sms_log. Never raises."""
    if not force:
        if not cfg.get("enabled") or not (cfg.get("events") or {}).get(event, False):
            return []
    if not is_configured(cfg):
        return []
    results = []
    for number in cfg.get("admin_numbers") or []:
        entry = {
            "id": str(uuid.uuid4()),
            "event": event,
            "to": number,
            "content": content[:480],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            res = await send_one(cfg, number, content)
            entry.update({
                "ok": res["ok"],
                "http_status": res["http_status"],
                "message_id": (res["response"] or {}).get("messageId") if isinstance(res["response"], dict) else None,
                "error": None if res["ok"] else str(res["response"])[:300],
            })
        except Exception as e:
            entry.update({"ok": False, "error": str(e)[:300]})
            logger.warning(f"SMS send failed ({event}) to ***{number[-4:]}: {e}")
        await db.sms_log.insert_one(dict(entry))
        entry.pop("_id", None)
        results.append(entry)
    return results


def redact(cfg: dict) -> dict:
    out = {**DEFAULT_SMS, **(cfg or {})}
    out["client_secret_set"] = bool((out.get("client_secret") or "").strip())
    out["client_secret"] = ""
    return out
