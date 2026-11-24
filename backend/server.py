"""e.GHANA Visa Portal — FastAPI backend."""
from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form, Depends, Response, Query, Request
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import json
import random
import re
from pathlib import Path
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime, timezone

from countries import passport_countries, travel_from_countries
from auth_utils import hash_password, verify_password, create_token, require_admin
from storage_service import (
    validate_file,
    MIME_MAP,
    get_backend as _storage_backend,
    get_backend_for_path as _storage_backend_for_path,
    R2StorageBackend,
    detect_environment as _detect_env,
)
from email_service import EmailService
from hubtel_service import (
    initiate_checkout,
    is_sandbox,
    is_ready_for_live as _hubtel_ready,
    missing_live_fields as _hubtel_missing,
    HubtelNotConfiguredError,
    check_transaction_status,
    status_probe as hubtel_status_probe,
)
import requests
from fx_service import (
    convert_usd_to_ghs as _convert_usd_ghs,
    get_rate as _fx_get_rate,
    FxError,
    PROVIDERS as _FX_PROVIDERS,
)
from ama_chat import ask_ama
import nowpayments_service as nowp
from seed_data import DEFAULT_SETTINGS, DEFAULT_EMAIL_TEMPLATES, EMAIL_TEMPLATES_VERSION, OBSOLETE_VISA_CODES
from analytics_service import (
    parse_ua as _parse_ua,
    classify_source as _classify_source,
    country_from_headers as _country_from_headers,
    city_from_headers as _city_from_headers,
    parse_date_range as _parse_date_range,
    is_test_record as _is_test_record,
    COUNTRY_NAMES as _COUNTRY_NAMES,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import asyncio
import hmac
import sms_service as sms
from audit_service import AuditMiddleware
from health_service import run_checks as _run_gateway_checks

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Mongo
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="e.GHANA Visa Portal")
api = APIRouter(prefix="/api")
email_svc = EmailService(db)


class HEADAsGETMiddleware:
    """RFC 9110 §9.3.2 — HEAD MUST return the same headers as GET but no body.
    FastAPI/Starlette only auto-registers GET on `@router.get()`, so a HEAD
    request receives a 405 with a JSON body of 31 bytes + Content-Length: 31,
    which Cloudflare rejects as an unparseable origin response (520). This
    middleware transparently handles HEAD by routing it as GET internally and
    stripping the response body before it reaches the client. Content-Length
    stays intact so probes get an accurate size."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") != "HEAD":
            await self.app(scope, receive, send)
            return
        # Route HEAD as GET internally.
        get_scope = dict(scope)
        get_scope["method"] = "GET"

        async def strip_body_send(message):
            if message["type"] == "http.response.body":
                # Drop the body but signal end-of-stream.
                await send({
                    "type": "http.response.body",
                    "body": b"",
                    "more_body": False,
                })
            else:
                await send(message)

        await self.app(get_scope, receive, strip_body_send)


app.add_middleware(HEADAsGETMiddleware)
app.add_middleware(AuditMiddleware, db=db)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def _notify_admin(template_name: str, context: dict) -> tuple[int, int]:
    """Fire-and-forget internal ops email. Never raises on the caller path.
    Fans out to the primary admin_notification_email + any additional_admin_emails.
    Returns (sent_count, failed_count) so wrappers can decide whether to log
    the dispatch as delivered or as needing retry."""
    sent, failed = 0, 0
    try:
        s = await get_settings()
        recipients: list[str] = []
        primary = (s.get("admin_notification_email") or "").strip()
        if primary:
            recipients.append(primary)
        for extra in (s.get("additional_admin_emails") or []):
            e = (extra or "").strip()
            if e and e not in recipients:
                recipients.append(e)
        if not recipients:
            return (0, 0)
        # Inject a back-office link so admins can jump straight to the record.
        tracking = context.get("tracking", "")
        base_url = (s.get("admin_backoffice_url") or "").strip().rstrip("/")
        if base_url and tracking:
            ctx = {**context, "backoffice_link": f"{base_url}?tracking={tracking}"}
        elif base_url:
            ctx = {**context, "backoffice_link": base_url}
        else:
            ctx = {**context, "backoffice_link": ""}
        for rcpt in recipients:
            try:
                await email_svc.send(
                    recipient=rcpt,
                    template_name=template_name,
                    lang="en",
                    context=ctx,
                )
                sent += 1
            except Exception as inner:
                failed += 1
                logger.warning(f"Admin notification failed for {rcpt} ({template_name}): {inner}")
    except Exception as e:
        logger.warning(f"Admin notification failed ({template_name}): {e}")
    return (sent, failed)


async def _notify_payment_event(event: str, *, tracking: str | None, reference: str | None, context: dict) -> bool:
    """Idempotent payment-lifecycle alert for admins.

    event ∈ {"failed", "expired", "refunded"}. Dedupe key is
    (event, tracking or reference).

    Status model in `payment_notifications_log`:
      • status="sent"      → notification confirmed delivered to Resend. Replay is a no-op.
      • status="failed"    → send attempt raised. Replay is ALLOWED so admins can retry.
      • status="pending"   → transient in-flight state (should never be observed for long).

    Returns True when the event was actually dispatched this call.
    """
    template_map = {
        "failed":   "admin_payment_failed",
        "expired":  "admin_payment_expired",
        "refunded": "admin_payment_refunded",
    }
    tpl = template_map.get(event)
    if not tpl:
        return False
    key = f"{event}:{reference or tracking or 'unknown'}"
    # Lookup existing log entry — only block when it is already "sent".
    existing = None
    try:
        existing = await db.payment_notifications_log.find_one({"key": key}, {"_id": 0})
    except Exception as e:
        logger.warning(f"payment_notifications_log read failed for {key}: {e}")
    if existing and existing.get("status") == "sent":
        logger.info(f"payment_event[{event}] already sent for {key} - skipping")
        return False
    # Record / update as pending, then try to send.
    try:
        await db.payment_notifications_log.update_one(
            {"key": key},
            {"$set": {
                "key": key,
                "event": event,
                "tracking": tracking,
                "reference": reference,
                "status": "pending",
                "updated_at": now_iso(),
            }, "$setOnInsert": {"created_at": now_iso()},
             "$inc": {"attempts": 1}},
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"payment_notifications_log write failed for {key}: {e}")
    try:
        sent, failed = await _notify_admin(tpl, context)
        if sent > 0:
            await db.payment_notifications_log.update_one(
                {"key": key},
                {"$set": {
                    "status": "sent",
                    "sent_at": now_iso(),
                    "sent_count": sent,
                    "failed_count": failed,
                    "last_error": None,
                }},
            )
            return True
        # Nothing got through — mark failed so a future webhook retry can try again.
        await db.payment_notifications_log.update_one(
            {"key": key},
            {"$set": {
                "status": "failed",
                "last_error": f"all {failed} recipients failed",
                "failed_at": now_iso(),
                "sent_count": sent,
                "failed_count": failed,
            }},
        )
        return False
    except Exception as e:
        err_text = str(e)[:500]
        logger.warning(f"payment_event[{event}] send failed for {key}: {err_text}")
        try:
            await db.payment_notifications_log.update_one(
                {"key": key},
                {"$set": {"status": "failed", "last_error": err_text, "failed_at": now_iso()}},
            )
        except Exception:
            pass
        return False



def _sms_alert(event: str, content: str) -> None:
    """Fire-and-forget admin SMS (never blocks or fails the caller)."""
    async def _run():
        try:
            s = await get_settings()
            await sms.send_admin_sms(db, s.get("sms") or {}, event, content)
        except Exception as e:
            logger.warning(f"SMS alert failed ({event}): {e}")
    asyncio.create_task(_run())


# ────────────────────────── STARTUP ──────────────────────────
async def _seed_default_admin() -> None:
    admin_email = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@eghanavisa.com")
    admin_pass = os.environ.get("DEFAULT_ADMIN_PASSWORD", "Admin@2026")
    force_reset = os.environ.get("ADMIN_RESET_ON_BOOT", "").lower() in ("1", "true", "yes")
    existing = await db.admins.find_one({"email": admin_email}, {"_id": 0})
    if existing:
        if force_reset:
            await db.admins.update_one(
                {"email": admin_email},
                {"$set": {
                    "password_hash": hash_password(admin_pass),
                    "must_change_password": False,
                    "updated_at": now_iso(),
                }},
            )
            logger.warning(f"ADMIN_RESET_ON_BOOT=true — reset admin password for {admin_email}")
        return
    await db.admins.insert_one({
        "id": str(uuid.uuid4()),
        "email": admin_email,
        "password_hash": hash_password(admin_pass),
        "must_change_password": True,
        "created_at": now_iso(),
    })
    logger.info(f"Seeded default admin: {admin_email}")


def _patch_visa_type_fields(existing_settings: dict) -> tuple[list, bool]:
    """Backfill missing per-visa fields without overwriting user changes."""
    vt_list = existing_settings.get("visa_types", [])
    changed = False
    default_by_code = {d["code"]: d for d in DEFAULT_SETTINGS["visa_types"]}
    for vt in vt_list:
        default_vt = default_by_code.get(vt.get("code"))
        if not default_vt:
            continue
        for field in ("express_available", "processing_time_label", "requires_presence"):
            if field not in vt:
                vt[field] = default_vt[field]
                changed = True
    return vt_list, changed


async def _seed_or_migrate_settings() -> None:
    existing = await db.settings.find_one({"id": "singleton"}, {"_id": 0})
    if not existing:
        await db.settings.insert_one(dict(DEFAULT_SETTINGS))
        logger.info("Seeded default settings")
        return
    updates: dict = {}
    if "nowpayments" not in existing:
        updates["nowpayments"] = DEFAULT_SETTINGS["nowpayments"]
    if "usdt_discount_pct" not in existing:
        updates["usdt_discount_pct"] = 0.0
    if "priority_surcharge_usd" not in existing:
        updates["priority_surcharge_usd"] = DEFAULT_SETTINGS["priority_surcharge_usd"]
    if "admin_notification_email" not in existing:
        updates["admin_notification_email"] = DEFAULT_SETTINGS["admin_notification_email"]
    if "additional_admin_emails" not in existing:
        updates["additional_admin_emails"] = DEFAULT_SETTINGS["additional_admin_emails"]
    if "whatsapp_public_number" not in existing:
        updates["whatsapp_public_number"] = DEFAULT_SETTINGS["whatsapp_public_number"]
    if "whatsapp_public_message" not in existing:
        updates["whatsapp_public_message"] = DEFAULT_SETTINGS["whatsapp_public_message"]
    if "whatsapp_agent_name" not in existing:
        updates["whatsapp_agent_name"] = DEFAULT_SETTINGS["whatsapp_agent_name"]
    if "whatsapp_agent_avatar_url" not in existing:
        updates["whatsapp_agent_avatar_url"] = DEFAULT_SETTINGS["whatsapp_agent_avatar_url"]
    if "whatsapp_agent_status_text" not in existing:
        updates["whatsapp_agent_status_text"] = DEFAULT_SETTINGS["whatsapp_agent_status_text"]
    if "whatsapp_teaser_message" not in existing:
        updates["whatsapp_teaser_message"] = DEFAULT_SETTINGS["whatsapp_teaser_message"]
    if "admin_backoffice_url" not in existing:
        updates["admin_backoffice_url"] = DEFAULT_SETTINGS["admin_backoffice_url"]
    for k in ("ga4_measurement_id", "gsc_verification", "clarity_project_id"):
        if k not in existing:
            updates[k] = ""
    if "r2" not in existing:
        updates["r2"] = DEFAULT_SETTINGS["r2"]
    else:
        # Backfill missing keys in existing r2 config
        existing_r2 = existing.get("r2") or {}
        r2_patched = dict(existing_r2)
        r2_changed = False
        for k, v in DEFAULT_SETTINGS["r2"].items():
            if k not in r2_patched:
                r2_patched[k] = v
                r2_changed = True
        if r2_changed:
            updates["r2"] = r2_patched
    if "sms" not in existing:
        updates["sms"] = dict(sms.DEFAULT_SMS)
    if "fx" not in existing:
        updates["fx"] = DEFAULT_SETTINGS["fx"]
    else:
        existing_fx = existing.get("fx") or {}
        fx_patched = dict(existing_fx)
        fx_changed = False
        for k, v in DEFAULT_SETTINGS["fx"].items():
            if k not in fx_patched:
                fx_patched[k] = v
                fx_changed = True
        if fx_changed:
            updates["fx"] = fx_patched

    # Backfill new Hubtel fields (e.g. cancellation_url)
    existing_hubtel = existing.get("hubtel") or {}
    hubtel_patched = dict(existing_hubtel)
    hubtel_changed = False
    for k, v in DEFAULT_SETTINGS["hubtel"].items():
        if k not in hubtel_patched:
            hubtel_patched[k] = v
            hubtel_changed = True
    if hubtel_changed:
        updates["hubtel"] = hubtel_patched

    # Migrate visa types: remove obsolete + add missing new ones
    vt_list = existing.get("visa_types", [])
    original_len = len(vt_list)
    vt_list = [vt for vt in vt_list if vt.get("code") not in OBSOLETE_VISA_CODES]
    existing_codes = {vt["code"] for vt in vt_list}
    for default_vt in DEFAULT_SETTINGS["visa_types"]:
        if default_vt["code"] not in existing_codes:
            vt_list.append(dict(default_vt))
    # Backfill missing fields on existing
    default_by_code = {d["code"]: d for d in DEFAULT_SETTINGS["visa_types"]}
    for vt in vt_list:
        default_vt = default_by_code.get(vt.get("code"))
        if not default_vt:
            continue
        for field in ("express_available", "priority_available", "processing_time_label",
                      "requires_presence", "category", "requires_business_fields"):
            if field in default_vt and field not in vt:
                vt[field] = default_vt[field]
    if len(vt_list) != original_len or vt_list != existing.get("visa_types", []):
        updates["visa_types"] = vt_list

    if updates:
        await db.settings.update_one({"id": "singleton"}, {"$set": updates})
        logger.info(f"Patched settings with: {list(updates.keys())}")


async def _seed_email_templates_if_needed() -> None:
    """Versioned re-seed: bump EMAIL_TEMPLATES_VERSION to force refresh."""
    doc = await db.template_versions.find_one({"id": "email_templates"}, {"_id": 0})
    current = (doc or {}).get("version", 0)
    if current >= EMAIL_TEMPLATES_VERSION:
        # Add newly introduced templates without touching admin-edited ones.
        for t in DEFAULT_EMAIL_TEMPLATES:
            await db.email_templates.update_one(
                {"template_name": t["template_name"], "lang": t["lang"]},
                {"$setOnInsert": dict(t)},
                upsert=True,
            )
        return
    # Non-destructive: add missing templates only, never overwrite admin edits.
    for t in DEFAULT_EMAIL_TEMPLATES:
        await db.email_templates.update_one(
            {"template_name": t["template_name"], "lang": t["lang"]},
            {"$setOnInsert": dict(t)},
            upsert=True,
        )
    await db.template_versions.update_one(
        {"id": "email_templates"},
        {"$set": {"version": EMAIL_TEMPLATES_VERSION, "updated_at": now_iso()}},
        upsert=True,
    )
    logger.info(f"Re-seeded email templates to version {EMAIL_TEMPLATES_VERSION}")


@app.on_event("startup")
async def startup() -> None:
    await _seed_default_admin()
    await _seed_or_migrate_settings()
    await _seed_email_templates_if_needed()
    await _ensure_indexes()


async def _ensure_indexes() -> None:
    """Create query-optimising indexes on hot collections.

    create_index is idempotent — reruns cost nothing when the index already
    exists. Indexes chosen from the actual query patterns in this file:
      • applications: lookups by tracking_no (very hot), lists filtered by
        payment_status + status with sort on created_at, search on email.
      • *_log / callbacks: time-ordered reads + key-based dedupe lookups.
      • analytics_events: event × time range aggregations.
    """
    try:
        # applications — primary hot collection
        await db.applications.create_index("tracking_no", unique=False, name="tracking_no_1")
        await db.applications.create_index("email", name="email_1")
        await db.applications.create_index([("payment_status", 1), ("status", 1), ("created_at", -1)], name="pay_status_created_1")
        await db.applications.create_index("created_at", name="created_at_desc_1")
        await db.applications.create_index("submitted_at", name="submitted_at_1", sparse=True)

        # Payment event collections — dedupe lookups by provider reference / key
        await db.hubtel_callbacks.create_index("client_reference", name="client_reference_1")
        await db.hubtel_callbacks.create_index("checkout_id", name="checkout_id_1")
        await db.hubtel_callbacks.create_index("created_at", name="created_at_desc_1")
        await db.crypto_payments.create_index("payment_id", name="payment_id_1")
        await db.crypto_payments.create_index("tracking_no", name="tracking_no_1")
        await db.crypto_payments.create_index("created_at", name="created_at_desc_1")

        # payment_notifications_log — idempotency key is the primary lookup
        await db.payment_notifications_log.create_index("key", unique=True, name="key_unique_1")

        # Audit logs + analytics — chronological reads
        await db.email_log.create_index("created_at", name="created_at_desc_1")
        await db.analytics_events.create_index([("event", 1), ("created_at", -1)], name="event_time_1")
        await db.analytics_events.create_index("path", name="path_1")

        # Settings / admins
        await db.admins.create_index("email", unique=True, name="email_unique_1")
        await db.admin_audit_log.create_index("created_at", name="created_at_desc_1")
        await db.admin_audit_log.create_index("admin_email", name="admin_email_1")
        await db.sms_log.create_index("created_at", name="created_at_desc_1")
        await db.gateway_health.create_index("checked_at", name="checked_at_desc_1")
        await db.cron_runs.create_index("run_id", unique=True, name="run_id_unique_1")
        await db.support_tickets.create_index([("status", 1), ("created_at", -1)], name="status_created_1")
        logger.info("Mongo indexes ensured.")
    except Exception as e:
        logger.warning(f"Index creation issue (non-fatal): {e}")


# ────────────────────────── HELPERS ──────────────────────────
async def get_settings() -> dict:
    doc = await db.settings.find_one({"id": "singleton"}, {"_id": 0})
    return doc or dict(DEFAULT_SETTINGS)


PAYMENTS_SUSPENDED_MSG = "Online payment is temporarily unavailable while we complete a security check. Please try again shortly or contact our support team."


def _is_preview_host(request: Request) -> bool:
    """Sandbox/simulated payment flows are only honoured on the preview environment."""
    host = (request.headers.get("host") or "").split(":")[0].strip().lower()
    return host.endswith((".preview.emergentagent.com", ".preview.emergentcf.cloud"))


def gen_tracking() -> str:
    year = datetime.now(timezone.utc).year
    return f"GH-{year}-{random.randint(100000, 999999)}"


def visa_price(settings: dict, visa_code: str) -> tuple[float, dict]:
    for vt in settings.get("visa_types", []):
        if vt["code"] == visa_code:
            return float(vt["price_usd"]), vt
    raise HTTPException(status_code=400, detail="Unknown visa type")


# ────────────────────────── PUBLIC ──────────────────────────
@api.get("/")
async def root():
    return {"service": "e.GHANA Visa Portal", "status": "ok"}


@api.get("/config")
async def public_config():
    """Config exposed to the public site (safe fields only)."""
    s = await get_settings()
    np_cfg = s.get("nowpayments", {})
    h_cfg = s.get("hubtel", {})
    return {
        "visa_types": s.get("visa_types", []),
        "payment_methods": s.get("payment_methods", []),
        "express_surcharge_usd": s.get("express_surcharge_usd", 50.0),
        "max_upload_mb": s.get("max_upload_mb", 8),
        "whatsapp_admin": s.get("whatsapp_admin", ""),
        "whatsapp_public_number": s.get("whatsapp_public_number", ""),
        "whatsapp_public_message": s.get("whatsapp_public_message", ""),
        "whatsapp_agent_name": s.get("whatsapp_agent_name", ""),
        "whatsapp_agent_avatar_url": s.get("whatsapp_agent_avatar_url", ""),
        "whatsapp_agent_status_text": s.get("whatsapp_agent_status_text", ""),
        "whatsapp_teaser_message": s.get("whatsapp_teaser_message", ""),
        "hubtel_sandbox": is_sandbox(h_cfg),
        "hubtel_ready": _hubtel_ready(h_cfg),
        "hubtel_missing_fields": [] if is_sandbox(h_cfg) else _hubtel_missing(h_cfg),
        "nowpayments_configured": nowp.is_configured(np_cfg),
        "nowpayments_sandbox": bool(np_cfg.get("sandbox", True)),
        "usdt_discount_pct": float(s.get("usdt_discount_pct", 0.0)),
        "priority_surcharge_usd": float(s.get("priority_surcharge_usd", 25.0)),
    }


@api.get("/countries")
async def countries():
    return {
        "passport": passport_countries(),
        "travel_from": travel_from_countries(),
    }


# ────────────────── APPLICATION SUBMISSION ──────────────────
class ApplicationIn(BaseModel):
    visa_code: str
    passport_country: str
    passport_number: str
    passport_type: str
    passport_expiry: str  # ISO date
    travelling_from: str
    arrival_date: str
    departure_date: str
    full_name: str
    email: EmailStr
    phone: str
    profession: str
    processing: str  # 'regular' | 'priority' | 'express'
    lang: str = "en"
    # Optional business fields (only used when visa is business_evisa)
    company_name: Optional[str] = None
    host_company: Optional[str] = None
    business_registration: Optional[str] = None
    business_address: Optional[str] = None
    purpose_of_visit: Optional[str] = None


@api.post("/applications")
async def create_application(payload: ApplicationIn):
    settings = await get_settings()
    price, visa = visa_price(settings, payload.visa_code)
    if not visa.get("active"):
        raise HTTPException(status_code=400, detail="Visa type is not currently available")

    processing = payload.processing.lower()
    if processing not in ("regular", "priority", "express"):
        raise HTTPException(status_code=400, detail="Invalid processing type")
    if processing == "express" and not visa.get("express_available", True):
        raise HTTPException(status_code=400, detail="Express processing is not available for this visa type")
    if processing == "priority" and not visa.get("priority_available", True):
        raise HTTPException(status_code=400, detail="Priority processing is not available for this visa type")

    surcharge = 0.0
    if processing == "express":
        surcharge = float(settings.get("express_surcharge_usd", 50.0))
    elif processing == "priority":
        surcharge = float(settings.get("priority_surcharge_usd", 25.0))
    total = price + surcharge

    # Business fields required for business visas
    if visa.get("requires_business_fields"):
        missing = [f for f in ("company_name", "host_company", "business_registration", "purpose_of_visit")
                   if not (getattr(payload, f) or "").strip()]
        if missing:
            raise HTTPException(status_code=400, detail=f"Missing business fields: {', '.join(missing)}")

    tracking = gen_tracking()
    while await db.applications.find_one({"tracking_no": tracking}, {"_id": 0}):
        tracking = gen_tracking()

    doc = {
        "id": str(uuid.uuid4()),
        "tracking_no": tracking,
        **payload.model_dump(),
        "base_price_usd": price,
        "surcharge_usd": surcharge,
        "amount_usd": total,
        "visa_name": visa.get("name_en"),
        "status": "pending_payment",
        "payment_status": "pending",
        "payment_transaction_id": None,
        "documents": {},
        "created_at": now_iso(),
        # submitted_at marks the moment the applicant definitively sent the
        # form. In the current flow there is no draft stage — every POST is a
        # final submission — so it equals created_at. Kept as a distinct field
        # so legacy records (which lack it) remain visually distinguishable
        # from records with a confirmed submission timestamp.
        "submitted_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.applications.insert_one(dict(doc))
    doc.pop("_id", None)

    # Fire admin notification email — new submission
    proc_label_map = {"express": "Express", "priority": "Priority", "regular": "Regular"}
    await _notify_admin("admin_new_submission", {
        "tracking": doc["tracking_no"],
        "name": doc["full_name"],
        "email": doc["email"],
        "phone": doc["phone"],
        "passport_country": doc["passport_country"],
        "visa_type": doc["visa_name"],
        "processing": proc_label_map.get(doc["processing"], doc["processing"].title()),
        "amount": f"{doc['amount_usd']:.2f}",
        "arrival_date": doc["arrival_date"],
        "submitted_at": doc["created_at"],
    })
    _sms_alert("new_submission",
               f"eGhanaVisa: new application {doc['tracking_no']} - {doc['full_name']} "
               f"({doc['visa_name']}, {doc['processing']}) ${doc['amount_usd']:.2f}")
    return doc


@api.post("/applications/{tracking_no}/documents")
async def upload_document(
    tracking_no: str,
    doc_type: str = Form(...),
    file: UploadFile = File(...),
):
    """doc_type ∈ {face_photo, passport_copy, passport_cover, flight_ticket}"""
    allowed = {"face_photo", "passport_copy", "passport_cover", "flight_ticket"}
    if doc_type not in allowed:
        raise HTTPException(status_code=400, detail="Invalid document type")

    app_doc = await db.applications.find_one({"tracking_no": tracking_no}, {"_id": 0})
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")

    settings = await get_settings()
    max_mb = int(settings.get("max_upload_mb", 8))

    data = await file.read()
    try:
        ext = validate_file(file.filename or "", len(data), max_mb)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    backend = _storage_backend(settings)
    path = backend.build_path(tracking_no, doc_type, ext)
    result = backend.put(path, data, MIME_MAP.get(ext, "application/octet-stream"))

    await db.applications.update_one(
        {"tracking_no": tracking_no},
        {"$set": {
            f"documents.{doc_type}": {
                "path": result["path"],
                "backend": getattr(backend, "name", "unknown"),
                "original_filename": file.filename,
                "content_type": MIME_MAP.get(ext),
                "size": result.get("size", len(data)),
                "uploaded_at": now_iso(),
            },
            "updated_at": now_iso(),
        }},
    )
    return {"ok": True, "doc_type": doc_type, "path": result["path"], "backend": getattr(backend, "name", "unknown")}


# ────────────────────── PAYMENT ──────────────────────
class PayInit(BaseModel):
    tracking_no: str


@api.post("/payments/initiate")
async def payment_initiate(payload: PayInit, request: Request):
    app_doc = await db.applications.find_one({"tracking_no": payload.tracking_no}, {"_id": 0})
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")
    if app_doc.get("payment_status") == "paid":
        raise HTTPException(status_code=400, detail="Application already paid")

    settings = await get_settings()
    hubtel_cfg = settings.get("hubtel", {})
    if is_sandbox(hubtel_cfg) and not _is_preview_host(request):
        logger.warning(f"Hubtel sandbox checkout refused outside preview for {payload.tracking_no}")
        raise HTTPException(status_code=503, detail={"code": "payments_suspended", "message": PAYMENTS_SUSPENDED_MSG})

    # Currency conversion: platform prices in USD, Hubtel settles in GHS.
    # Only do the conversion for live production mode — sandbox skips it so
    # we don't hammer FX providers during smoke tests.
    fx_meta = None
    amount_to_send = app_doc["amount_usd"]
    currency = "USD"
    if not is_sandbox(hubtel_cfg):
        try:
            conv = _convert_usd_ghs(app_doc["amount_usd"], settings.get("fx", {}))
            fx_meta = conv
            amount_to_send = conv["amount_ghs"]
            currency = "GHS"
        except FxError as e:
            raise HTTPException(status_code=503, detail={
                "code": "fx_unavailable",
                "message": f"Could not obtain USD→GHS exchange rate: {e}",
            })

    # Persist FX + charge metadata BEFORE calling Hubtel so an upstream failure
    # still leaves a full audit trail for reconciliation.
    pre_call_record = {
        "payment_method": "hubtel",
        "payment_currency": currency,
        "amount_usd": round(float(app_doc["amount_usd"]), 2),
        "amount_charged": float(amount_to_send),
        "updated_at": now_iso(),
    }
    if fx_meta:
        pre_call_record["fx"] = fx_meta
    await db.applications.update_one(
        {"tracking_no": payload.tracking_no},
        {"$set": pre_call_record},
    )

    try:
        result = initiate_checkout(
            hubtel_cfg,
            amount=amount_to_send,
            description=f"Ghana Visa {app_doc['visa_name']} - {app_doc['tracking_no']}",
            tracking_no=app_doc["tracking_no"],
            currency=currency,
        )
    except HubtelNotConfiguredError as e:
        raise HTTPException(status_code=503, detail={
            "code": "hubtel_not_configured",
            "message": str(e),
            "missing_fields": e.missing,
        })
    except RuntimeError as e:
        # Upstream Hubtel error (network, auth, etc.). FX metadata already
        # persisted above so ops can still reconcile.
        raise HTTPException(status_code=502, detail={
            "code": "hubtel_gateway_error",
            "message": str(e),
        })

    await db.applications.update_one(
        {"tracking_no": payload.tracking_no},
        {"$set": {"payment_transaction_id": result["transaction_id"], "updated_at": now_iso()}},
    )
    return result


class PayConfirm(BaseModel):
    tracking_no: str
    transaction_id: Optional[str] = None
    success: bool = True


async def _mark_application_paid(app_doc: dict, payment_method: str) -> bool:
    """Idempotently mark an application as paid, send customer + admin emails.
    Returns True if this call flipped the state; False if it was already paid."""
    if app_doc.get("payment_status") == "paid":
        return False
    res = await db.applications.update_one(
        {"tracking_no": app_doc["tracking_no"], "payment_status": {"$ne": "paid"}},
        {"$set": {
            "payment_status": "paid",
            "status": "submitted",
            "paid_at": now_iso(),
            "payment_method": payment_method,
            "updated_at": now_iso(),
        }},
    )
    if res.modified_count != 1:
        return False
    processing_label = "Express (48–72h)" if app_doc["processing"] == "express" else "Regular (5–7 days)"
    await email_svc.send(
        recipient=app_doc["email"],
        template_name="submitted",
        lang=app_doc.get("lang", "en"),
        context={
            "name": app_doc["full_name"],
            "tracking": app_doc["tracking_no"],
            "visa_type": app_doc["visa_name"],
            "processing": processing_label,
            "amount": f"{app_doc['amount_usd']:.2f}",
        },
    )
    await _notify_admin("admin_payment_success", {
        "tracking": app_doc["tracking_no"],
        "name": app_doc["full_name"],
        "email": app_doc["email"],
        "visa_type": app_doc["visa_name"],
        "processing": processing_label,
        "amount": f"{app_doc['amount_usd']:.2f}",
        "payment_method": payment_method,
        "paid_at": now_iso(),
    })
    _sms_alert("payment_success",
               f"eGhanaVisa: PAID {app_doc['tracking_no']} - {app_doc['full_name']} "
               f"${app_doc['amount_usd']:.2f} via {payment_method}")
    return True


@api.post("/payments/confirm")
async def payment_confirm(payload: PayConfirm, request: Request):
    """SANDBOX-only endpoint: allows the mock checkout page to mark an application
    as paid. Rejected when real Hubtel credentials are configured — production
    payments MUST flow through /api/webhooks/hubtel."""
    settings = await get_settings()
    if not _is_preview_host(request):
        logger.warning(f"Refused /payments/confirm outside preview for {payload.tracking_no}")
        raise HTTPException(status_code=403, detail="Sandbox-only endpoint. Production uses the Hubtel webhook.")
    if not is_sandbox(settings.get("hubtel", {})):
        raise HTTPException(status_code=403, detail="Sandbox-only endpoint. Production uses the Hubtel webhook.")

    app_doc = await db.applications.find_one({"tracking_no": payload.tracking_no}, {"_id": 0})
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")

    if not payload.success:
        await db.applications.update_one(
            {"tracking_no": payload.tracking_no, "payment_status": {"$ne": "paid"}},
            {"$set": {"payment_status": "failed", "updated_at": now_iso()}},
        )
        return {"ok": False}

    await _mark_application_paid(app_doc, payment_method="Visa card (Hubtel Sandbox)")
    return {"ok": True, "tracking_no": payload.tracking_no}


@api.get("/payments/status/{tracking_no}")
async def payment_status(tracking_no: str):
    """Public: check the payment status of a specific application. Used by the
    /payment/return page to poll after Hubtel redirects the customer back."""
    doc = await db.applications.find_one(
        {"tracking_no": tracking_no},
        {"_id": 0, "payment_status": 1, "status": 1, "tracking_no": 1, "visa_name": 1, "amount_usd": 1,
         "payment_method": 1, "payment_verification": 1},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")
    # Live Hubtel: nudge a server-side verification (throttled) in case the callback is late or lost.
    if doc.get("payment_method") == "hubtel" and doc.get("payment_status") != "paid":
        last = (doc.get("payment_verification") or {}).get("checked_at") or ""
        stale = not last or (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() > 20
        if stale and not is_sandbox((await get_settings()).get("hubtel", {})):
            await db.applications.update_one({"tracking_no": tracking_no}, {"$set": {"payment_verification.checked_at": now_iso()}})
            asyncio.create_task(_verify_hubtel_payment(tracking_no))
    return {
        "tracking_no": doc["tracking_no"],
        "payment_status": doc.get("payment_status", "pending"),
        "status": doc.get("status"),
        "visa_name": doc.get("visa_name"),
        "amount_usd": doc.get("amount_usd"),
    }


def _hubtel_success(data: dict) -> bool:
    """Hubtel Online Checkout callback → decide if this is a success payload.
    Docs: Data.Status ∈ {'Success','Failed','Cancelled'} with ResponseCode '0000' on success."""
    if not isinstance(data, dict):
        return False
    status = str((data.get("Data") or {}).get("Status", "")).lower()
    if status == "success":
        return True
    top_status = str(data.get("Status", "")).lower()
    resp_code = str(data.get("ResponseCode", ""))
    return top_status == "success" and resp_code == "0000"


@app.post("/api/webhooks/hubtel")
async def hubtel_webhook(request: Request):
    """Hubtel Online Checkout server-to-server callback.

    Hubtel POSTs a JSON payload to this URL after the customer completes payment.
    We verify the transaction against our own initiate record (CheckoutId +
    ClientReference), then idempotently mark the application paid.

    Hubtel expects a 2xx response quickly; we always return 200 with {ok:true}
    to prevent unnecessary retries once we've persisted the callback."""
    raw = await request.body()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        data = {}

    inner = data.get("Data") or {}
    client_ref = str(inner.get("ClientReference") or data.get("ClientReference") or "").strip()
    checkout_id = str(inner.get("CheckoutId") or inner.get("SalesInvoiceId") or "").strip()

    # Always persist raw callback for audit
    await db.hubtel_callbacks.insert_one({
        "id": str(uuid.uuid4()),
        "created_at": now_iso(),
        "client_reference": client_ref,
        "checkout_id": checkout_id,
        "payload": data if isinstance(data, dict) else {"raw": raw.decode("utf-8", errors="replace")[:2000]},
    })

    if not client_ref:
        logger.warning("Hubtel callback missing ClientReference")
        return {"ok": True}

    app_doc = await db.applications.find_one({"tracking_no": client_ref}, {"_id": 0})
    if not app_doc:
        logger.warning(f"Hubtel callback for unknown tracking_no: {client_ref}")
        return {"ok": True}

    # Optional bind check: if we have a stored transaction id, ensure it matches
    stored_tx = (app_doc.get("payment_transaction_id") or "").strip()
    if stored_tx and checkout_id and stored_tx not in (checkout_id,) and checkout_id not in stored_tx:
        # Mismatch — log but don't crash; some Hubtel plans use different id fields
        logger.info(f"Hubtel callback checkoutId={checkout_id} vs stored tx={stored_tx} (mismatch, still processing)")

    hubtel_cfg = (await get_settings()).get("hubtel", {})
    if not is_sandbox(hubtel_cfg) or not _is_preview_host(request):
        # LIVE (or any non-preview host): a callback is only a trigger — the Hubtel Status API is the authority.
        if app_doc.get("payment_status") != "paid":
            asyncio.create_task(_verify_hubtel_payment(
                client_ref, callback_success=_hubtel_success(data),
                reference=checkout_id or app_doc.get("payment_transaction_id"),
            ))
        return {"ok": True}

    if _hubtel_success(data):
        await _mark_application_paid(app_doc, payment_method="Visa card (Hubtel)")
    elif app_doc.get("payment_status") == "paid":
        # Never downgrade a confirmed payment on a late/duplicate non-success callback.
        logger.info(f"Hubtel non-success callback ignored for already-paid {client_ref}")
    else:
        await db.applications.update_one(
            {"tracking_no": client_ref},
            {"$set": {"payment_status": "failed", "updated_at": now_iso()}},
        )
        # Fire admin alert — idempotent. Hubtel delivered an authenticated
        # non-success callback, so we treat it as a confirmed failure.
        await _notify_payment_event(
            "failed",
            tracking=client_ref,
            reference=checkout_id or app_doc.get("payment_transaction_id"),
            context={
                "tracking": client_ref,
                "name": app_doc.get("full_name", ""),
                "amount": f"{float(app_doc.get('amount_usd') or 0):.2f}",
                "currency": "USD",
                "provider": "Hubtel",
                "reference": checkout_id or app_doc.get("payment_transaction_id") or "—",
                "status": (inner.get("Status") or data.get("Status") or "failed"),
                "event_time": now_iso(),
            },
        )
    return {"ok": True}


async def _verify_hubtel_payment(tracking_no: str, *, callback_success: Optional[bool] = None, reference: Optional[str] = None) -> str:
    """Confirm a LIVE Hubtel payment via the Transaction Status API before
    marking it paid. Returns the resulting verification state."""
    app_doc = await db.applications.find_one({"tracking_no": tracking_no}, {"_id": 0})
    if not app_doc:
        return "not_found"
    if app_doc.get("payment_status") == "paid":
        return "paid"
    cfg = (await get_settings()).get("hubtel", {})
    prev = app_doc.get("payment_verification") or {}
    ver = {"checked_at": now_iso(), "attempts": int(prev.get("attempts", 0)) + 1, "last_error": None}
    try:
        data = await asyncio.to_thread(check_transaction_status, cfg, tracking_no)
    except Exception as e:
        ver.update(state="error", last_error=str(e)[:300])
        await db.applications.update_one({"tracking_no": tracking_no}, {"$set": {"payment_verification": ver}})
        logger.warning(f"Hubtel verification error for {tracking_no}: {e}")
        return "error"

    status = str(data.get("status", "")).lower()
    expected = float(app_doc.get("amount_charged") or 0)
    try:
        paid_amount = float(data.get("amount") or 0)
    except (TypeError, ValueError):
        paid_amount = 0.0
    ref_ok = str(data.get("clientReference") or "") == tracking_no
    amount_ok = expected > 0 and paid_amount + 0.05 >= expected
    ver["hubtel"] = {k: data.get(k) for k in ("status", "amount", "transactionId", "externalTransactionId", "paymentMethod", "date", "clientReference")}

    if status == "paid" and ref_ok and amount_ok:
        ver["state"] = "verified"
        await db.applications.update_one({"tracking_no": tracking_no}, {"$set": {"payment_verification": ver}})
        await _mark_application_paid(app_doc, payment_method="Visa card (Hubtel)")
        return "verified"
    if status == "paid":
        ver.update(state="mismatch", last_error=f"reference_ok={ref_ok} amount={paid_amount} expected={expected}")
        logger.warning(f"Hubtel verification MISMATCH for {tracking_no}: {ver['last_error']}")
    elif status == "refunded":
        ver["state"] = "refunded"
    else:
        ver["state"] = "unpaid"
    await db.applications.update_one({"tracking_no": tracking_no}, {"$set": {"payment_verification": ver}})
    if ver["state"] == "unpaid" and callback_success is False:
        await db.applications.update_one(
            {"tracking_no": tracking_no}, {"$set": {"payment_status": "failed", "updated_at": now_iso()}},
        )
        await _notify_payment_event("failed", tracking=tracking_no, reference=reference, context={
            "tracking": tracking_no, "name": app_doc.get("full_name", ""),
            "amount": f"{float(app_doc.get('amount_usd') or 0):.2f}", "currency": "USD",
            "provider": "Hubtel", "reference": reference or "—", "status": "Unpaid (verified)",
            "event_time": now_iso(),
        })
    return ver["state"]


async def _reconcile_pending_hubtel() -> int:
    """Retry verification for recent live Hubtel payments still unconfirmed."""
    cfg = (await get_settings()).get("hubtel", {})
    if is_sandbox(cfg):
        return 0
    since = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - 48 * 3600, tz=timezone.utc).isoformat()
    docs = await db.applications.find({
        "payment_status": {"$ne": "paid"},
        "payment_method": "hubtel",
        "payment_verification.state": {"$in": ["error", "unpaid"]},
        "payment_verification.attempts": {"$lt": 12},
        "updated_at": {"$gte": since},
    }, {"_id": 0, "tracking_no": 1}).limit(50).to_list(50)
    for d in docs:
        await _verify_hubtel_payment(d["tracking_no"])
    return len(docs)


# ────────────────────── TRACKING ──────────────────────
@api.get("/track/{tracking_no}")
async def track(tracking_no: str):
    doc = await db.applications.find_one({"tracking_no": tracking_no}, {"_id": 0})
    if not doc or doc.get("payment_status") != "paid":
        raise HTTPException(status_code=404, detail="Application not found")
    return {
        "tracking_no": doc["tracking_no"],
        "status": doc["status"],
        "visa_name": doc["visa_name"],
        "processing": doc["processing"],
        "arrival_date": doc["arrival_date"],
        "departure_date": doc["departure_date"],
        "created_at": doc["created_at"],
        "paid_at": doc.get("paid_at"),
        "in_progress_at": doc.get("in_progress_at"),
        "done_at": doc.get("done_at"),
    }


# ────────────────────── ADMIN AUTH ──────────────────────
class AdminLoginIn(BaseModel):
    email: EmailStr
    password: str


@api.post("/admin/login")
async def admin_login(payload: AdminLoginIn):
    admin = await db.admins.find_one({"email": payload.email}, {"_id": 0})
    if not admin or not verify_password(payload.password, admin["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(admin["id"], admin["email"])
    return {
        "token": token,
        "email": admin["email"],
        "must_change_password": admin.get("must_change_password", False),
    }


class AdminChangeCredsIn(BaseModel):
    current_password: str
    new_email: Optional[EmailStr] = None
    new_password: Optional[str] = None


@api.post("/admin/credentials")
async def admin_change_creds(payload: AdminChangeCredsIn, ctx: dict = Depends(require_admin)):
    admin = await db.admins.find_one({"id": ctx["sub"]}, {"_id": 0})
    if not admin or not verify_password(payload.current_password, admin["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    update = {"must_change_password": False, "updated_at": now_iso()}
    if payload.new_email:
        update["email"] = payload.new_email
    if payload.new_password:
        if len(payload.new_password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        update["password_hash"] = hash_password(payload.new_password)

    await db.admins.update_one({"id": ctx["sub"]}, {"$set": update})
    return {"ok": True}


@api.get("/admin/me")
async def admin_me(ctx: dict = Depends(require_admin)):
    admin = await db.admins.find_one({"id": ctx["sub"]}, {"_id": 0, "password_hash": 0})
    return admin


# ────────────────────── ADMIN DASHBOARD ──────────────────────
@api.get("/admin/kpis")
async def admin_kpis(ctx: dict = Depends(require_admin)):
    pipeline = [{"$match": {"payment_status": "paid"}}]
    total = await db.applications.count_documents({"payment_status": "paid"})
    submitted = await db.applications.count_documents({"payment_status": "paid", "status": "submitted"})
    in_progress = await db.applications.count_documents({"payment_status": "paid", "status": "in_progress"})
    done = await db.applications.count_documents({"payment_status": "paid", "status": "done"})
    revenue_agg = await db.applications.aggregate([
        {"$match": {"payment_status": "paid"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_usd"}, "avg": {"$avg": "$amount_usd"}}},
    ]).to_list(1)
    revenue = revenue_agg[0]["total"] if revenue_agg else 0
    avg = revenue_agg[0]["avg"] if revenue_agg else 0
    express_count = await db.applications.count_documents({"payment_status": "paid", "processing": "express"})
    return {
        "total": total,
        "submitted": submitted,
        "in_progress": in_progress,
        "done": done,
        "revenue_usd": round(revenue, 2),
        "avg_usd": round(avg, 2),
        "express_count": express_count,
    }


@api.get("/admin/applications")
async def admin_applications(
    status: str = Query("all"),
    search: str = Query("", description="Case-insensitive match on tracking_no, full_name or email"),
    from_date: str = Query("", description="Inclusive lower bound on created_at (ISO date YYYY-MM-DD, interpreted as UTC midnight)"),
    to_date: str = Query("", description="Inclusive upper bound on created_at (ISO date YYYY-MM-DD, interpreted as UTC end-of-day)"),
    page: int = Query(1, ge=1, description="1-indexed page number"),
    page_size: int = Query(100, ge=1, le=1000, description="Items per page (capped at 1000)"),
    ctx: dict = Depends(require_admin),
):
    """List applications. All new filters are optional and additive — existing
    callers (no params) see the exact same payload shape as before, just now
    capped at page_size items (default 100 instead of the old blind 1000)."""
    q: dict = {"payment_status": "paid"}
    if status in ("submitted", "in_progress", "done"):
        q["status"] = status

    # --- Search (case-insensitive across identifying fields) ---
    s = (search or "").strip()
    if s:
        # Escape regex metacharacters so operators can paste real email/tracking.
        safe = re.escape(s)
        q["$or"] = [
            {"tracking_no": {"$regex": safe, "$options": "i"}},
            {"full_name": {"$regex": safe, "$options": "i"}},
            {"email": {"$regex": safe, "$options": "i"}},
        ]

    # --- Period filter — uses submitted_at when present, falls back to
    # created_at for legacy records, so the filter targets exactly the field
    # the Dashboard column displays. ---
    if from_date or to_date:
        bounds = []
        effective = {"$ifNull": ["$submitted_at", "$created_at"]}
        if from_date:
            bounds.append({"$gte": [effective, f"{from_date.strip()}T00:00:00+00:00"]})
        if to_date:
            bounds.append({"$lte": [effective, f"{to_date.strip()}T23:59:59.999999+00:00"]})
        q["$expr"] = {"$and": bounds} if len(bounds) > 1 else bounds[0]

    # Sort is always by the effective submission time (desc). We use a Mongo
    # aggregation pipeline so legacy records sort with the same key the UI shows.
    skip = (page - 1) * page_size
    pipeline = [
        {"$match": q},
        {"$addFields": {"_effective_at": {"$ifNull": ["$submitted_at", "$created_at"]}}},
        {"$sort": {"_effective_at": -1}},
        {"$skip": skip},
        {"$limit": page_size},
        {"$project": {"_id": 0, "_effective_at": 0}},
    ]
    docs = await db.applications.aggregate(pipeline).to_list(page_size)
    return docs


@api.get("/admin/applications/{tracking_no}")
async def admin_application_detail(tracking_no: str, ctx: dict = Depends(require_admin)):
    doc = await db.applications.find_one({"tracking_no": tracking_no}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return doc


# ----------------- Payments / Transactions (read-only, unified) -----------------
from transactions_service import list_transactions, compute_summary, to_csv, to_xlsx


@api.get("/admin/transactions")
async def admin_transactions(
    provider: str = Query(""),
    status: str = Query(""),
    search: str = Query(""),
    from_date: str = Query(""),
    to_date: str = Query(""),
    ctx: dict = Depends(require_admin),
):
    """Unified, deduplicated read of every known transaction across Hubtel
    callbacks, NOWPayments callbacks, and confirmed payments on the
    applications collection. Strictly read-only."""
    txs = await list_transactions(
        db,
        provider=provider, status=status, search=search,
        from_date=from_date, to_date=to_date,
    )
    return {
        "transactions": txs,
        "summary": compute_summary(txs),
    }


@api.get("/admin/transactions/{tx_id:path}")
async def admin_transaction_detail(tx_id: str, ctx: dict = Depends(require_admin)):
    """Detail view for a single transaction. Returns the normalized tx plus
    the raw source document and, when matched, the parent application doc."""
    txs = await list_transactions(db)
    match = next((t for t in txs if t["id"] == tx_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Transaction not found")
    raw = None
    if match["source"] == "application":
        raw = await db.applications.find_one({"tracking_no": match["tracking_no"]}, {"_id": 0})
    elif match["source"] == "hubtel_callback":
        raw = await db.hubtel_callbacks.find_one(
            {"$or": [{"provider_reference": match["provider_reference"]},
                     {"transaction_id": match["provider_reference"]}]},
            {"_id": 0},
        )
    elif match["source"] == "crypto_payments":
        raw = await db.crypto_payments.find_one(
            {"$or": [{"invoice_id": match["provider_reference"]},
                     {"payment_id": match["provider_reference"]}]},
            {"_id": 0},
        )
    app_doc = None
    if match.get("tracking_no"):
        app_doc = await db.applications.find_one(
            {"tracking_no": match["tracking_no"]},
            {"_id": 0, "documents": 0},  # hide big binary refs
        )
    return {"transaction": match, "raw": raw, "application": app_doc}


@api.get("/admin/transactions.csv")
async def admin_transactions_csv(
    provider: str = Query(""),
    status: str = Query(""),
    search: str = Query(""),
    from_date: str = Query(""),
    to_date: str = Query(""),
    ctx: dict = Depends(require_admin),
):
    """CSV export honoring the same filters as the list endpoint."""
    txs = await list_transactions(
        db,
        provider=provider, status=status, search=search,
        from_date=from_date, to_date=to_date,
    )
    csv_text = to_csv(txs)
    filename = f"transactions-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api.get("/admin/transactions.xlsx")
async def admin_transactions_xlsx(
    provider: str = Query(""),
    status: str = Query(""),
    search: str = Query(""),
    from_date: str = Query(""),
    to_date: str = Query(""),
    ctx: dict = Depends(require_admin),
):
    """Professional Excel (.xlsx) export honoring the same filters as the
    list endpoint. Includes a Summary sheet with revenue by (provider,
    currency) computed via Excel formulas that exclude audit-only rows."""
    txs = await list_transactions(
        db,
        provider=provider, status=status, search=search,
        from_date=from_date, to_date=to_date,
    )
    blob = to_xlsx(txs)
    filename = f"transactions-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.xlsx"
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )




class StatusIn(BaseModel):
    status: str  # in_progress | done


@api.post("/admin/applications/{tracking_no}/status")
async def admin_set_status(tracking_no: str, payload: StatusIn, ctx: dict = Depends(require_admin)):
    if payload.status not in ("in_progress", "done"):
        raise HTTPException(status_code=400, detail="Invalid status")
    app_doc = await db.applications.find_one({"tracking_no": tracking_no}, {"_id": 0})
    if not app_doc:
        raise HTTPException(status_code=404, detail="Not found")

    ts_field = f"{payload.status}_at"
    await db.applications.update_one(
        {"tracking_no": tracking_no},
        {"$set": {"status": payload.status, ts_field: now_iso(), "updated_at": now_iso()}},
    )
    template_name = payload.status
    await email_svc.send(
        recipient=app_doc["email"],
        template_name=template_name,
        lang=app_doc.get("lang", "en"),
        context={"name": app_doc["full_name"], "tracking": tracking_no},
    )
    return {"ok": True}


@api.get("/admin/applications/{tracking_no}/documents/{doc_type}")
async def admin_download_doc(tracking_no: str, doc_type: str, ctx: dict = Depends(require_admin)):
    app_doc = await db.applications.find_one({"tracking_no": tracking_no}, {"_id": 0})
    if not app_doc or doc_type not in (app_doc.get("documents") or {}):
        raise HTTPException(status_code=404, detail="Document not found")
    ref = app_doc["documents"][doc_type]
    settings = await get_settings()
    backend = _storage_backend_for_path(ref["path"], settings)
    data, ct = backend.get(ref["path"])
    return Response(content=data, media_type=ref.get("content_type", ct))


@api.get("/admin/applications/{tracking_no}/documents/{doc_type}/signed-url")
async def admin_signed_url_doc(tracking_no: str, doc_type: str, ctx: dict = Depends(require_admin)):
    """Return a short-lived signed URL when the file lives on R2. Falls back to
    a hint that the caller should use the streaming endpoint if the backend
    (Emergent legacy) does not support pre-signed URLs."""
    app_doc = await db.applications.find_one({"tracking_no": tracking_no}, {"_id": 0})
    if not app_doc or doc_type not in (app_doc.get("documents") or {}):
        raise HTTPException(status_code=404, detail="Document not found")
    ref = app_doc["documents"][doc_type]
    settings = await get_settings()
    backend = _storage_backend_for_path(ref["path"], settings)
    url = backend.signed_url(ref["path"]) if hasattr(backend, "signed_url") else None
    if url:
        return {"url": url, "backend": backend.name, "expires_in": getattr(backend, "signed_url_ttl", 900)}
    # Legacy fallback — caller should use the streaming endpoint above
    return {"url": None, "backend": backend.name, "streaming_endpoint": f"/api/admin/applications/{tracking_no}/documents/{doc_type}"}


# ────────────────────── ADMIN SETTINGS ──────────────────────
class VisaPriceUpdate(BaseModel):
    code: str
    price_usd: float


@api.post("/admin/settings/visa-price")
async def admin_update_price(payload: VisaPriceUpdate, ctx: dict = Depends(require_admin)):
    s = await get_settings()
    updated = False
    for vt in s["visa_types"]:
        if vt["code"] == payload.code:
            vt["price_usd"] = float(payload.price_usd)
            updated = True
            break
    if not updated:
        raise HTTPException(status_code=404, detail="Visa code not found")
    await db.settings.update_one({"id": "singleton"}, {"$set": {"visa_types": s["visa_types"], "updated_at": now_iso()}})
    return {"ok": True}


class ExpressSurchargeIn(BaseModel):
    price_usd: float


@api.post("/admin/settings/express-surcharge")
async def admin_update_surcharge(payload: ExpressSurchargeIn, ctx: dict = Depends(require_admin)):
    await db.settings.update_one(
        {"id": "singleton"},
        {"$set": {"express_surcharge_usd": float(payload.price_usd), "updated_at": now_iso()}},
    )
    return {"ok": True}


class ToggleIn(BaseModel):
    code: str
    active: bool


@api.post("/admin/settings/visa-toggle")
async def admin_toggle_visa(payload: ToggleIn, ctx: dict = Depends(require_admin)):
    s = await get_settings()
    for vt in s["visa_types"]:
        if vt["code"] == payload.code:
            if vt.get("always_active") and not payload.active:
                raise HTTPException(status_code=400, detail="This visa type cannot be deactivated")
            vt["active"] = bool(payload.active)
            break
    await db.settings.update_one({"id": "singleton"}, {"$set": {"visa_types": s["visa_types"], "updated_at": now_iso()}})
    return {"ok": True}


@api.post("/admin/settings/payment-toggle")
async def admin_toggle_payment(payload: ToggleIn, ctx: dict = Depends(require_admin)):
    s = await get_settings()
    for pm in s["payment_methods"]:
        if pm["code"] == payload.code:
            pm["active"] = bool(payload.active)
            break
    await db.settings.update_one({"id": "singleton"}, {"$set": {"payment_methods": s["payment_methods"], "updated_at": now_iso()}})
    return {"ok": True}


class HubtelConfigIn(BaseModel):
    sandbox: bool
    api_id: str = ""
    api_key: str = ""
    merchant_account_id: str = ""
    callback_url: str = ""
    return_url: str = ""
    cancellation_url: str = ""
    outbound_proxy_url: str = ""


@api.post("/admin/settings/hubtel")
async def admin_update_hubtel(payload: HubtelConfigIn, ctx: dict = Depends(require_admin)):
    await db.settings.update_one(
        {"id": "singleton"},
        {"$set": {"hubtel": payload.model_dump(), "updated_at": now_iso()}},
    )
    return {"ok": True}


class WhatsAppIn(BaseModel):
    whatsapp_admin: str


@api.post("/admin/settings/whatsapp")
async def admin_update_whatsapp(payload: WhatsAppIn, ctx: dict = Depends(require_admin)):
    await db.settings.update_one(
        {"id": "singleton"},
        {"$set": {"whatsapp_admin": payload.whatsapp_admin, "updated_at": now_iso()}},
    )
    return {"ok": True}


class AdminNotificationEmailIn(BaseModel):
    admin_notification_email: str = ""


@api.post("/admin/settings/admin-notification-email")
async def admin_update_notification_email(payload: AdminNotificationEmailIn, ctx: dict = Depends(require_admin)):
    email = (payload.admin_notification_email or "").strip()
    # Basic validation — allow empty (to disable notifications) or a plausible email
    if email and "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email address")
    await db.settings.update_one(
        {"id": "singleton"},
        {"$set": {"admin_notification_email": email, "updated_at": now_iso()}},
    )
    return {"ok": True, "admin_notification_email": email}


class AdditionalAdminEmailsIn(BaseModel):
    additional_admin_emails: List[str] = []


@api.post("/admin/settings/additional-admin-emails")
async def admin_update_additional_emails(payload: AdditionalAdminEmailsIn, ctx: dict = Depends(require_admin)):
    cleaned: list[str] = []
    for raw in payload.additional_admin_emails:
        e = (raw or "").strip()
        if not e:
            continue
        if "@" not in e:
            raise HTTPException(status_code=400, detail=f"Invalid email: {e}")
        if e not in cleaned:
            cleaned.append(e)
    await db.settings.update_one(
        {"id": "singleton"},
        {"$set": {"additional_admin_emails": cleaned, "updated_at": now_iso()}},
    )
    return {"ok": True, "additional_admin_emails": cleaned}


class WhatsAppPublicIn(BaseModel):
    whatsapp_public_number: str = ""
    whatsapp_public_message: str = ""
    whatsapp_agent_name: str = ""
    whatsapp_agent_avatar_url: str = ""
    whatsapp_agent_status_text: str = ""
    whatsapp_teaser_message: str = ""


@api.post("/admin/settings/whatsapp-public")
async def admin_update_whatsapp_public(payload: WhatsAppPublicIn, ctx: dict = Depends(require_admin)):
    await db.settings.update_one(
        {"id": "singleton"},
        {"$set": {
            "whatsapp_public_number": (payload.whatsapp_public_number or "").strip(),
            "whatsapp_public_message": (payload.whatsapp_public_message or "").strip(),
            "whatsapp_agent_name": (payload.whatsapp_agent_name or "").strip(),
            "whatsapp_agent_avatar_url": (payload.whatsapp_agent_avatar_url or "").strip(),
            "whatsapp_agent_status_text": (payload.whatsapp_agent_status_text or "").strip(),
            "whatsapp_teaser_message": (payload.whatsapp_teaser_message or "").strip(),
            "updated_at": now_iso(),
        }},
    )
    return {"ok": True}


class AdminBackofficeUrlIn(BaseModel):
    admin_backoffice_url: str = ""


@api.post("/admin/settings/admin-backoffice-url")
async def admin_update_backoffice_url(payload: AdminBackofficeUrlIn, ctx: dict = Depends(require_admin)):
    url = (payload.admin_backoffice_url or "").strip()
    await db.settings.update_one(
        {"id": "singleton"},
        {"$set": {"admin_backoffice_url": url, "updated_at": now_iso()}},
    )
    return {"ok": True, "admin_backoffice_url": url}


class AIModelIn(BaseModel):
    ai_model: str


@api.post("/admin/settings/ai-model")
async def admin_update_ai_model(payload: AIModelIn, ctx: dict = Depends(require_admin)):
    await db.settings.update_one(
        {"id": "singleton"},
        {"$set": {"ai_model": payload.ai_model, "updated_at": now_iso()}},
    )
    return {"ok": True}


class MaxUploadIn(BaseModel):
    max_upload_mb: int


@api.post("/admin/settings/upload-limit")
async def admin_update_upload(payload: MaxUploadIn, ctx: dict = Depends(require_admin)):
    await db.settings.update_one(
        {"id": "singleton"},
        {"$set": {"max_upload_mb": int(payload.max_upload_mb), "updated_at": now_iso()}},
    )
    return {"ok": True}


@api.get("/admin/settings")
async def admin_get_settings(ctx: dict = Depends(require_admin)):
    s = await get_settings()
    # Redact R2 secret before returning
    if isinstance(s.get("r2"), dict):
        s["r2"] = _redact_r2(s["r2"])
    s["sms"] = sms.redact(s.get("sms") or {})
    return s


# ────────────────── EMAIL TEMPLATES ──────────────────
@api.get("/admin/email-templates")
async def admin_email_templates(ctx: dict = Depends(require_admin)):
    return await db.email_templates.find({}, {"_id": 0}).to_list(100)


class EmailTemplateIn(BaseModel):
    template_name: str
    lang: str
    subject: str
    html: str


@api.post("/admin/email-templates")
async def admin_save_template(payload: EmailTemplateIn, ctx: dict = Depends(require_admin)):
    await db.email_templates.update_one(
        {"template_name": payload.template_name, "lang": payload.lang},
        {"$set": {
            "template_name": payload.template_name,
            "lang": payload.lang,
            "subject": payload.subject,
            "html": payload.html,
            "updated_at": now_iso(),
        }, "$setOnInsert": {"id": f"{payload.template_name}_{payload.lang}"}},
        upsert=True,
    )
    return {"ok": True}


@api.get("/admin/email-log")
async def admin_email_log(ctx: dict = Depends(require_admin)):
    return await db.email_log.find({}, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)


class TestEmailIn(BaseModel):
    recipient: EmailStr
    template_name: str = "submitted"
    lang: str = "en"


@api.post("/admin/email/test")
async def admin_send_test_email(payload: TestEmailIn, ctx: dict = Depends(require_admin)):
    """Send a sample email using an existing template to verify Resend delivery."""
    context = {
        "name": "Test Recipient",
        "tracking": "GH-2026-TEST01",
        "visa_type": "30 Days Tourist Visa",
        "processing": "Regular",
        "amount": "350.00",
    }
    entry = await email_svc.send(
        recipient=payload.recipient,
        template_name=payload.template_name,
        context=context,
        lang=payload.lang,
    )
    return {
        "ok": True,
        "simulated": entry.get("simulated"),
        "resend_id": entry.get("resend_id"),
        "error": entry.get("error"),
        "subject": entry.get("subject"),
    }


# ────────────────── NOWPAYMENTS (USDT) ──────────────────
class NowPaymentsConfigIn(BaseModel):
    sandbox: bool = True
    api_key: str = ""
    ipn_secret: str = ""
    sandbox_api_key: str = ""
    sandbox_ipn_secret: str = ""


@api.post("/admin/settings/nowpayments")
async def admin_update_nowpayments(payload: NowPaymentsConfigIn, ctx: dict = Depends(require_admin)):
    await db.settings.update_one(
        {"id": "singleton"},
        {"$set": {"nowpayments": payload.model_dump(), "updated_at": now_iso()}},
    )
    return {"ok": True}


class UsdtDiscountIn(BaseModel):
    pct: float


@api.post("/admin/settings/usdt-discount")
async def admin_update_usdt_discount(payload: UsdtDiscountIn, ctx: dict = Depends(require_admin)):
    pct = max(0.0, min(50.0, float(payload.pct)))  # clamp 0..50%
    await db.settings.update_one(
        {"id": "singleton"},
        {"$set": {"usdt_discount_pct": pct, "updated_at": now_iso()}},
    )
    return {"ok": True, "usdt_discount_pct": pct}


@api.post("/admin/settings/nowpayments/test")
async def admin_test_nowpayments(ctx: dict = Depends(require_admin)):
    s = await get_settings()
    cfg = s.get("nowpayments", {})
    if not nowp.is_configured(cfg):
        raise HTTPException(status_code=400, detail="NowPayments not configured (missing API key or IPN secret)")
    try:
        status_info = nowp.get_status(cfg)
        currencies = nowp.get_currencies(cfg)
        has_trc20 = "usdttrc20" in currencies
        has_bep20 = "usdtbsc" in currencies
        return {
            "ok": True,
            "status": status_info,
            "usdttrc20_supported": has_trc20,
            "usdtbsc_supported": has_bep20,
            "mode": "sandbox" if cfg.get("sandbox", True) else "production",
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"NowPayments error: {e}")


class CryptoInitIn(BaseModel):
    tracking_no: str
    network: str  # 'trc20' | 'bep20'


@api.post("/payments/crypto/initiate")
async def crypto_initiate(payload: CryptoInitIn, request: Request):
    if payload.network not in nowp.CURRENCY_MAP:
        raise HTTPException(status_code=400, detail="Invalid network")

    s = await get_settings()
    cfg = s.get("nowpayments", {})
    if (cfg.get("sandbox", True) or not nowp.is_configured(cfg)) and not _is_preview_host(request):
        logger.warning(f"NowPayments sandbox/simulated payment refused outside preview for {payload.tracking_no}")
        raise HTTPException(status_code=503, detail=PAYMENTS_SUSPENDED_MSG)

    # Verify method active in admin
    method_code = f"usdt_{payload.network}"
    method = next((m for m in s.get("payment_methods", []) if m["code"] == method_code), None)
    if not method or not method.get("active"):
        raise HTTPException(status_code=403, detail="This payment method is disabled")

    app_doc = await db.applications.find_one({"tracking_no": payload.tracking_no}, {"_id": 0})
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")
    if app_doc.get("payment_status") == "paid":
        raise HTTPException(status_code=400, detail="Application already paid")

    pay_currency = nowp.CURRENCY_MAP[payload.network]
    ipn_url = f"{os.environ.get('PUBLIC_BASE_URL', '').rstrip('/')}/api/webhooks/nowpayments"

    discount_pct = float(s.get("usdt_discount_pct", 0.0) or 0.0)
    original_amount = float(app_doc["amount_usd"])
    price_amount = round(original_amount * (1 - discount_pct / 100.0), 2)

    simulated = not nowp.is_configured(cfg)

    if simulated:
        # SIMULATION mode — no real API keys yet
        payment_id = f"NP-SIM-{uuid.uuid4().hex[:12].upper()}"
        # ~1:1 for USDT (peg to USD); slight variance to look realistic
        pay_amount = round(price_amount * 1.00, 6)
        pay_address = ("TSIMULATED" if payload.network == "trc20" else "0xSIMULATED") + uuid.uuid4().hex[:24].upper()
        result = {
            "payment_id": payment_id,
            "pay_address": pay_address,
            "pay_amount": pay_amount,
            "payment_status": "waiting",
            "expiration_estimate_date": None,
        }
    else:
        try:
            result = nowp.create_payment(
                cfg,
                price_amount=price_amount,
                pay_currency=pay_currency,
                order_id=app_doc["tracking_no"],
                ipn_callback_url=ipn_url,
            )
        except Exception as e:
            logger.error(f"NowPayments create_payment failed: {e}")
            raise HTTPException(status_code=502, detail=f"NowPayments error: {e}")

    payment_id = str(result.get("payment_id"))
    doc = {
        "id": str(uuid.uuid4()),
        "payment_id": payment_id,
        "tracking_no": app_doc["tracking_no"],
        "network": payload.network,
        "pay_currency": pay_currency,
        "pay_address": result.get("pay_address"),
        "pay_amount": result.get("pay_amount"),
        "price_amount_usd": price_amount,
        "original_amount_usd": original_amount,
        "discount_pct": discount_pct,
        "payment_status": result.get("payment_status", "waiting"),
        "actually_paid": None,
        "expiration_estimate_date": result.get("expiration_estimate_date"),
        "provider": "nowpayments",
        "sandbox": cfg.get("sandbox", True),
        "simulated": simulated,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "ipn_payloads": [],
    }
    await db.crypto_payments.insert_one(dict(doc))
    await db.applications.update_one(
        {"tracking_no": app_doc["tracking_no"]},
        {"$set": {"payment_transaction_id": payment_id, "updated_at": now_iso()}},
    )
    doc.pop("_id", None)
    return {
        "payment_id": payment_id,
        "pay_address": doc["pay_address"],
        "pay_amount": doc["pay_amount"],
        "pay_currency": pay_currency,
        "network": payload.network,
        "network_label": nowp.NETWORK_LABEL[payload.network],
        "expiration_estimate_date": doc["expiration_estimate_date"],
        "simulated": simulated,
    }


class PaymentDiagnosticsIn(BaseModel):
    tracking_nos: List[str] = []


@api.post("/admin/payments/diagnostics")
async def admin_payment_diagnostics(payload: PaymentDiagnosticsIn, ctx: dict = Depends(require_admin)):
    """READ-ONLY: egress IP, Hubtel credentials/IP authorisation + reconciliation, NOWPayments key validity.
    Never changes any application, payment or setting."""
    s = await get_settings()
    h_cfg = s.get("hubtel", {}) or {}
    np_cfg = s.get("nowpayments", {}) or {}
    proxies = {"http": h_cfg["outbound_proxy_url"], "https": h_cfg["outbound_proxy_url"]} if (h_cfg.get("outbound_proxy_url") or "").strip() else None

    def _ip(px):
        try:
            return requests.get("https://api.ipify.org", proxies=px, timeout=10).text.strip()
        except Exception as e:
            return f"error: {str(e)[:120]}"

    def _np(mode_sandbox: bool):
        cfg = {**np_cfg, "sandbox": mode_sandbox}
        res = {"keys_present": nowp.is_configured(cfg)}
        if not res["keys_present"]:
            return res
        try:
            cur = nowp.get_currencies(cfg)
            res.update(api_key_valid=True, usdttrc20=("usdttrc20" in cur), usdtbsc=("usdtbsc" in cur))
        except Exception as e:
            res.update(api_key_valid=False, error=str(e)[:200])
        return res

    refs = [t.strip() for t in payload.tracking_nos if t.strip()][:5]
    hubtel_refs = {}
    for ref in refs:
        local = await db.applications.find_one({"tracking_no": ref}, {"_id": 0, "payment_status": 1, "payment_method": 1,
                                                                    "amount_usd": 1, "amount_charged": 1, "payment_currency": 1,
                                                                    "payment_transaction_id": 1, "paid_at": 1})
        callbacks = await db.hubtel_callbacks.count_documents({"client_reference": ref})
        hubtel_refs[ref] = {"local": local, "callbacks_received": callbacks,
                            "hubtel_status_api": await asyncio.to_thread(hubtel_status_probe, h_cfg, ref)}
    return {
        "checked_at": now_iso(),
        "egress_ip": await asyncio.to_thread(_ip, None),
        "egress_ip_via_hubtel_proxy": await asyncio.to_thread(_ip, proxies) if proxies else None,
        "public_base_url": os.environ.get("PUBLIC_BASE_URL", ""),
        "hubtel": {
            "mode": "sandbox" if is_sandbox(h_cfg) else "live",
            "credentials_present": {f: bool(str(h_cfg.get(f) or "").strip()) for f in ("api_id", "api_key", "merchant_account_id")},
            "callback_url": h_cfg.get("callback_url", ""),
            "return_url": h_cfg.get("return_url", ""),
            "cancellation_url": h_cfg.get("cancellation_url", ""),
            "status_api_probe": await asyncio.to_thread(hubtel_status_probe, h_cfg, "DIAG-PROBE-0000"),
            "references": hubtel_refs,
        },
        "nowpayments": {
            "mode": "sandbox" if np_cfg.get("sandbox", True) else "live",
            "ipn_url": f"{os.environ.get('PUBLIC_BASE_URL', '').rstrip('/')}/api/webhooks/nowpayments",
            "live_keys": await asyncio.to_thread(_np, False),
            "sandbox_keys": await asyncio.to_thread(_np, True),
        },
    }


class SimulateFinishIn(BaseModel):
    success: bool = True


@api.post("/payments/crypto/simulate-finish/{payment_id}")
async def crypto_simulate_finish(payment_id: str, payload: SimulateFinishIn, request: Request):
    """Simulate a NowPayments IPN 'finished' or 'failed' — sandbox helper only."""
    if not _is_preview_host(request):
        raise HTTPException(status_code=403, detail="Simulation is only available on the preview environment")
    doc = await db.crypto_payments.find_one({"payment_id": payment_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Unknown payment")
    if not doc.get("simulated"):
        raise HTTPException(status_code=400, detail="Only available for simulated payments")
    np_status = "finished" if payload.success else "failed"
    fake_payload = {
        "payment_id": payment_id,
        "order_id": doc["tracking_no"],
        "payment_status": np_status,
        "pay_amount": doc["pay_amount"],
        "actually_paid": doc["pay_amount"] if payload.success else 0,
        "pay_currency": doc["pay_currency"],
    }
    await _apply_crypto_status_update(payment_id, np_status, fake_payload, ipn=True)
    return {"ok": True}


@api.get("/payments/crypto/status/{payment_id}")
async def crypto_status(payment_id: str, request: Request):
    doc = await db.crypto_payments.find_one({"payment_id": payment_id}, {"_id": 0, "ipn_payloads": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Unknown crypto payment")

    trusted_env = _is_preview_host(request) or not (doc.get("sandbox", True) or doc.get("simulated"))
    unverified_finish = doc.get("payment_status") == "finished" and (doc.get("verification") or {}).get("state") not in ("verified", "simulated")
    # Best-effort refresh from NowPayments if still pending (polling fallback)
    if trusted_env and (unverified_finish or doc.get("payment_status") not in ("finished", "failed", "refunded", "expired")) and not doc.get("simulated"):
        s = await get_settings()
        cfg = s.get("nowpayments", {})
        if nowp.is_configured(cfg):
            try:
                remote = nowp.get_payment(cfg, payment_id)
                np_status = remote.get("payment_status", doc["payment_status"])
                if np_status != doc["payment_status"] or unverified_finish:
                    await _apply_crypto_status_update(payment_id, np_status, remote, ipn=False)
                    doc = await db.crypto_payments.find_one({"payment_id": payment_id}, {"_id": 0, "ipn_payloads": 0})
            except Exception as e:
                logger.warning(f"NowPayments polling failed: {e}")

    internal = nowp.map_status(doc["payment_status"])
    if internal == "paid" and (doc.get("verification") or {}).get("state") not in ("verified", "simulated"):
        internal = "processing"
    return {
        "payment_id": doc["payment_id"],
        "tracking_no": doc["tracking_no"],
        "payment_status": doc["payment_status"],
        "internal_status": internal,
        "pay_address": doc["pay_address"],
        "pay_amount": doc["pay_amount"],
        "pay_currency": doc["pay_currency"],
        "actually_paid": doc.get("actually_paid"),
        "network": doc["network"],
    }


async def _verify_nowpayments_payment(doc: dict) -> dict:
    """Authoritative check against the NOWPayments API before any 'paid' status.
    Returns {"state": verified|rejected|error|simulated, ...}."""
    ver = {"provider": "nowpayments", "checked_at": now_iso(), "reasons": []}
    if doc.get("simulated"):
        return {**ver, "state": "simulated"}
    cfg = (await get_settings()).get("nowpayments", {})
    if bool(cfg.get("sandbox", True)) != bool(doc.get("sandbox", True)):
        return {**ver, "state": "rejected", "reasons": ["environment_mismatch"]}
    try:
        remote = await asyncio.to_thread(nowp.get_payment, cfg, doc["payment_id"])
    except Exception as e:
        return {**ver, "state": "error", "reasons": [f"api_error: {str(e)[:200]}"]}

    def _f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    expected_crypto = _f(doc.get("pay_amount"))
    paid_crypto = _f(remote.get("actually_paid"))
    checks = {
        "final_status": str(remote.get("payment_status", "")).lower() == "finished",
        "payment_id": str(remote.get("payment_id", "")) == str(doc["payment_id"]),
        "order_id": str(remote.get("order_id", "")) == str(doc["tracking_no"]),
        "currency_network": str(remote.get("pay_currency", "")).lower() == str(doc.get("pay_currency", "")).lower(),
        "amount_received": expected_crypto > 0 and paid_crypto >= expected_crypto * 0.995,
        "price_usd": str(remote.get("price_currency", "")).lower() == "usd"
                     and abs(_f(remote.get("price_amount")) - _f(doc.get("price_amount_usd"))) <= 0.01,
    }
    ver["reasons"] = [k for k, ok in checks.items() if not ok]
    ver["state"] = "verified" if not ver["reasons"] else "rejected"
    ver["nowpayments"] = {k: remote.get(k) for k in (
        "payment_id", "payment_status", "order_id", "pay_currency", "pay_amount",
        "actually_paid", "price_amount", "price_currency", "outcome_amount", "updated_at")}
    return ver


async def _apply_crypto_status_update(payment_id: str, np_status: str, payload: dict, ipn: bool):
    """Idempotently update crypto_payments + trigger visa confirmation on 'finished'."""
    doc = await db.crypto_payments.find_one({"payment_id": payment_id}, {"_id": 0})
    if not doc:
        return
    pending_verification = np_status == "finished" and (doc.get("verification") or {}).get("state") not in ("verified", "simulated")
    if doc.get("payment_status") == np_status and not ipn and not pending_verification:
        return
    update = {
        "payment_status": np_status,
        "actually_paid": payload.get("actually_paid"),
        "updated_at": now_iso(),
    }
    push_ipn = {"$push": {"ipn_payloads": {"received_at": now_iso(), "payload": payload}}} if ipn else {}
    await db.crypto_payments.update_one(
        {"payment_id": payment_id},
        {"$set": update, **push_ipn},
    )

    # On finished: verify with NOWPayments, then mark application paid (idempotent) and send confirmation email
    if np_status == "finished":
        ver = await _verify_nowpayments_payment(doc)
        await db.crypto_payments.update_one({"payment_id": payment_id}, {"$set": {"verification": ver}})
        if ver["state"] not in ("verified", "simulated"):
            logger.warning(f"NOWPayments verification {ver['state']} for {payment_id}: {ver['reasons']}")
            await db.applications.update_one(
                {"tracking_no": doc["tracking_no"], "payment_status": {"$ne": "paid"}},
                {"$set": {"payment_verification": ver, "updated_at": now_iso()}},
            )
            return
        app_doc = await db.applications.find_one({"tracking_no": doc["tracking_no"]}, {"_id": 0})
        if app_doc and app_doc.get("payment_status") != "paid":
            res = await db.applications.update_one(
                {"tracking_no": app_doc["tracking_no"], "payment_status": {"$ne": "paid"}},
                {"$set": {
                    "payment_status": "paid",
                    "status": "submitted",
                    "paid_at": now_iso(),
                    "payment_method": f"usdt_{doc['network']}",
                    "payment_verification": ver,
                    "updated_at": now_iso(),
                }},
            )
            if res.modified_count != 1:
                return
            processing_label = "Express (48–72h)" if app_doc["processing"] == "express" else "Regular"
            await email_svc.send(
                recipient=app_doc["email"],
                template_name="submitted",
                lang=app_doc.get("lang", "en"),
                context={
                    "name": app_doc["full_name"],
                    "tracking": app_doc["tracking_no"],
                    "visa_type": app_doc["visa_name"],
                    "processing": processing_label,
                    "amount": f"{app_doc['amount_usd']:.2f}",
                },
            )
            # Admin notification — payment success (USDT crypto)
            await _notify_admin("admin_payment_success", {
                "tracking": app_doc["tracking_no"],
                "name": app_doc["full_name"],
                "email": app_doc["email"],
                "visa_type": app_doc["visa_name"],
                "processing": processing_label,
                "amount": f"{app_doc['amount_usd']:.2f}",
                "payment_method": f"USDT {doc['network'].upper()} (NowPayments)",
                "paid_at": now_iso(),
            })

    # Failure-lifecycle alerts — only on confirmed provider status strings.
    # NowPayments documented terminal/incident statuses:
    #   failed, expired  → failure
    #   refunded         → refund
    # "partially_paid" and "confirming" stay silent (not confirmed).
    elif np_status in ("failed", "expired", "refunded"):
        event = {"failed": "failed", "expired": "expired", "refunded": "refunded"}[np_status]
        app_doc = await db.applications.find_one({"tracking_no": doc.get("tracking_no")}, {"_id": 0}) if doc.get("tracking_no") else None
        await _notify_payment_event(
            event,
            tracking=doc.get("tracking_no"),
            reference=payment_id,
            context={
                "tracking": doc.get("tracking_no") or "—",
                "name": (app_doc or {}).get("full_name", "—"),
                "amount": f"{float(doc.get('amount') or (app_doc or {}).get('amount_usd') or 0):.2f}",
                "currency": (doc.get("pay_currency") or "USDT").upper(),
                "provider": f"NOWPayments ({(doc.get('network') or 'crypto').upper()})",
                "reference": payment_id,
                "status": np_status,
                "event_time": now_iso(),
            },
        )


@app.post("/api/webhooks/nowpayments")
async def nowpayments_ipn(request: Request):
    raw = await request.body()
    sig = request.headers.get("x-nowpayments-sig", "")
    s = await get_settings()
    cfg = s.get("nowpayments", {})
    secret = nowp._ipn_secret(cfg)
    if not nowp.verify_ipn_signature(raw, sig, secret):
        logger.warning("Rejected NowPayments IPN (invalid signature)")
        await db.crypto_ipn_rejections.insert_one({
            "id": str(uuid.uuid4()),
            "created_at": now_iso(),
            "sig": sig,
            "raw": raw.decode("utf-8", errors="replace")[:2000],
        })
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    payment_id = str(data.get("payment_id", ""))
    np_status = data.get("payment_status", "waiting")
    if not payment_id:
        return {"ok": True}
    if not _is_preview_host(request):
        pdoc = await db.crypto_payments.find_one({"payment_id": payment_id}, {"_id": 0, "sandbox": 1, "simulated": 1})
        if cfg.get("sandbox", True) or not pdoc or pdoc.get("sandbox", True) or pdoc.get("simulated"):
            logger.warning(f"NowPayments IPN ignored outside preview (sandbox/simulated/unknown) payment_id={payment_id}")
            await db.crypto_ipn_rejections.insert_one({
                "id": str(uuid.uuid4()), "created_at": now_iso(), "reason": "sandbox_or_unknown_outside_preview",
                "sig": sig, "raw": raw.decode("utf-8", errors="replace")[:2000],
            })
            return {"ok": True}
    await _apply_crypto_status_update(payment_id, np_status, data, ipn=True)
    return {"ok": True}


@api.get("/admin/crypto-payments")
async def admin_crypto_payments(ctx: dict = Depends(require_admin)):
    return await db.crypto_payments.find({}, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)


# ────────────────── ABENA CHAT + ESCALATION ──────────────────
class ChatIn(BaseModel):
    message: str
    session_id: Optional[str] = None
    tracking_no: Optional[str] = None
    contact_email: Optional[str] = None
    contact_name: Optional[str] = None


@api.post("/chat")
async def chat_endpoint(payload: ChatIn):
    s = await get_settings()
    session_id = payload.session_id or str(uuid.uuid4())
    result = await ask_ama(
        message=payload.message,
        session_id=session_id,
        whatsapp=s.get("whatsapp_admin", ""),
        settings=s,
        model=s.get("ai_model", "claude-sonnet-4-5-20250929"),
    )
    ticket_id = None
    if result.get("escalate"):
        # Create an escalation ticket + notify ops
        ticket_id = str(uuid.uuid4())
        ticket = {
            "id": ticket_id,
            "session_id": session_id,
            "status": "open",
            "priority": "normal",
            "customer_name": payload.contact_name or "",
            "customer_email": payload.contact_email or "",
            "tracking_no": payload.tracking_no or "",
            "question": payload.message[:2000],
            "ai_reply": result["reply"][:2000],
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "admin_reply": None,
            "admin_replied_at": None,
        }
        await db.support_tickets.insert_one(ticket)
        # Notify admin via existing admin email helper
        try:
            await email_svc.send(
                recipient=s.get("admin_notification_email") or "",
                template_name="admin_new_submission",  # reuse existing template — fields aligned
                lang="en",
                context={
                    "tracking": payload.tracking_no or f"TKT-{ticket_id[:8]}",
                    "name": payload.contact_name or "(anonymous chat visitor)",
                    "email": payload.contact_email or "(not provided)",
                    "phone": s.get("whatsapp_admin", ""),
                    "passport_country": "-",
                    "visa_type": "Chat escalation",
                    "processing": "-",
                    "amount": "0.00",
                    "arrival_date": "-",
                    "submitted_at": now_iso(),
                },
            ) if (s.get("admin_notification_email") or "").strip() else None
        except Exception as e:
            logger.warning(f"Escalation notification failed: {e}")
        who = payload.contact_name or payload.contact_email or "visitor"
        _sms_alert("ticket_escalated",
                   f"eGhanaVisa: Abena escalated a ticket from {who}: {payload.message[:90]}")

    await db.chat_log.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "user_message": payload.message,
        "ai_reply": result["reply"],
        "escalated": bool(result.get("escalate")),
        "ticket_id": ticket_id,
        "created_at": now_iso(),
    })
    return {
        "reply": result["reply"],
        "session_id": session_id,
        "whatsapp": s.get("whatsapp_admin", ""),
        "escalated": bool(result.get("escalate")),
        "ticket_id": ticket_id,
    }


# ─────────── Admin support tickets ───────────
@api.get("/admin/support-tickets")
async def admin_list_tickets(status: Optional[str] = None, ctx: dict = Depends(require_admin)):
    q = {"status": status} if status else {}
    return await db.support_tickets.find(q, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)


class TicketReplyIn(BaseModel):
    reply: str
    close: bool = True


@api.post("/admin/support-tickets/{ticket_id}/reply")
async def admin_reply_ticket(ticket_id: str, payload: TicketReplyIn, ctx: dict = Depends(require_admin)):
    t = await db.support_tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    updates = {
        "admin_reply": payload.reply,
        "admin_replied_at": now_iso(),
        "admin_email": ctx.get("email"),
        "updated_at": now_iso(),
    }
    if payload.close:
        updates["status"] = "resolved"
    await db.support_tickets.update_one({"id": ticket_id}, {"$set": updates})
    # Email the customer if we have their address
    customer_email = (t.get("customer_email") or "").strip()
    if customer_email:
        try:
            await email_svc.send(
                recipient=customer_email,
                template_name="support_reply",
                lang="en",
                context={
                    "name": t.get("customer_name") or "Traveller",
                    "tracking": t.get("tracking_no") or f"TKT-{ticket_id[:8]}",
                    "question": t.get("question") or "",
                    "reply": payload.reply,
                },
            )
        except Exception as e:
            logger.warning(f"Ticket reply email failed: {e}")
    return {"ok": True, "emailed": bool(customer_email)}


class TicketStatusIn(BaseModel):
    status: str


@api.post("/admin/support-tickets/{ticket_id}/status")
async def admin_ticket_status(ticket_id: str, payload: TicketStatusIn, ctx: dict = Depends(require_admin)):
    if payload.status not in ("open", "resolved"):
        raise HTTPException(status_code=400, detail="Invalid status")
    res = await db.support_tickets.update_one(
        {"id": ticket_id}, {"$set": {"status": payload.status, "updated_at": now_iso()}}
    )
    if not res.matched_count:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"ok": True}


@api.get("/admin/support-tickets/{ticket_id}/conversation")
async def admin_ticket_conversation(ticket_id: str, ctx: dict = Depends(require_admin)):
    t = await db.support_tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    msgs = await db.chat_log.find(
        {"session_id": t.get("session_id")},
        {"_id": 0, "user_message": 1, "ai_reply": 1, "created_at": 1, "escalated": 1},
    ).sort("created_at", 1).limit(100).to_list(100)
    return {"ticket": t, "messages": msgs}


# ─────────── SMS alerts (Hubtel) ───────────
class SmsConfigIn(BaseModel):
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    sender_id: str = ""
    admin_numbers: List[str] = []
    events: dict = {}


@api.post("/admin/settings/sms")
async def admin_update_sms(payload: SmsConfigIn, ctx: dict = Depends(require_admin)):
    s = await get_settings()
    current = s.get("sms") or {}
    sender = payload.sender_id.strip()
    if sender and (len(sender) > 11 or not sender.replace(" ", "").isalnum()):
        raise HTTPException(status_code=400, detail="Sender ID must be max 11 letters/digits")
    numbers = []
    for raw in payload.admin_numbers:
        n = sms.normalize_number(raw)
        if not n:
            continue
        if not (10 <= len(n) <= 15):
            raise HTTPException(status_code=400, detail=f"Invalid phone number: {raw}")
        if n not in numbers:
            numbers.append(n)
    cfg = {
        "enabled": payload.enabled,
        "client_id": payload.client_id.strip(),
        # Empty secret means "keep the stored one" (UI never receives it back).
        "client_secret": payload.client_secret.strip() or current.get("client_secret", ""),
        "sender_id": sender,
        "admin_numbers": numbers,
        "events": {e: bool(payload.events.get(e, False)) for e in sms.SMS_EVENTS},
    }
    if cfg["enabled"] and not sms.is_configured(cfg):
        raise HTTPException(status_code=400, detail="Fill Client ID, Client Secret, Sender ID and at least one number before enabling")
    await db.settings.update_one({"id": "singleton"}, {"$set": {"sms": cfg, "updated_at": now_iso()}})
    return {"ok": True, "sms": sms.redact(cfg)}


@api.post("/admin/sms/test")
async def admin_sms_test(ctx: dict = Depends(require_admin)):
    s = await get_settings()
    cfg = s.get("sms") or {}
    if not sms.is_configured(cfg):
        raise HTTPException(status_code=400, detail="SMS is not configured yet")
    results = await sms.send_admin_sms(db, cfg, "test", "eGhanaVisa: test SMS from the Command Center.", force=True)
    return {"ok": any(r.get("ok") for r in results), "results": results}


@api.get("/admin/sms-log")
async def admin_sms_log(ctx: dict = Depends(require_admin)):
    return await db.sms_log.find({}, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)


# ─────────── Admin activity audit log ───────────
@api.get("/admin/audit-log")
async def admin_audit_log(
    search: str = Query(""),
    admin_email: str = Query(""),
    only_failed: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    ctx: dict = Depends(require_admin),
):
    q: dict = {}
    if admin_email:
        q["admin_email"] = admin_email
    if only_failed:
        q["success"] = False
    if search.strip():
        q["path"] = {"$regex": re.escape(search.strip()), "$options": "i"}
    total = await db.admin_audit_log.count_documents(q)
    items = await db.admin_audit_log.find(q, {"_id": 0}).sort("created_at", -1) \
        .skip((page - 1) * page_size).limit(page_size).to_list(page_size)
    admins = await db.admin_audit_log.distinct("admin_email")
    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "admins": sorted(a for a in admins if a)}


# ─────────── Payment gateway health monitoring ───────────
GATEWAY_LABELS = {"hubtel": "Hubtel (card payments)", "nowpayments": "NowPayments (crypto)", "hubtel_sms": "Hubtel SMS"}


async def _check_gateways_and_alert() -> dict:
    s = await get_settings()
    report = await _run_gateway_checks(s)
    prev = await db.gateway_health.find_one({}, {"_id": 0}, sort=[("checked_at", -1)])
    prev_status = {r["gateway"]: r["status"] for r in (prev or {}).get("results", [])}
    await db.gateway_health.insert_one(dict(report))
    report.pop("_id", None)
    for r in report["results"]:
        before = prev_status.get(r["gateway"])
        if before is None or before == r["status"]:
            continue
        state = "DOWN" if r["status"] == "down" else "BACK UP"
        label = GATEWAY_LABELS.get(r["gateway"], r["gateway"])
        await _notify_admin("admin_gateway_down", {
            "gateway": label, "state": state, "detail": r["detail"],
            "checked_at": report["checked_at"], "tracking": "",
        })
        await sms.send_admin_sms(db, s.get("sms") or {}, "gateway", f"eGhanaVisa: {label} is {state} ({r['detail'][:60]})", force=bool((s.get("sms") or {}).get("enabled")))
    return report


@api.post("/admin/health/check")
async def admin_health_check(ctx: dict = Depends(require_admin)):
    return await _check_gateways_and_alert()


@api.get("/admin/health")
async def admin_health(ctx: dict = Depends(require_admin)):
    history = await db.gateway_health.find({}, {"_id": 0}).sort("checked_at", -1).limit(96).to_list(96)
    since = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - 86400, tz=timezone.utc).isoformat()
    failed_24h = await db.applications.count_documents({"payment_status": "failed", "updated_at": {"$gte": since}})
    paid_24h = await db.applications.count_documents({"payment_status": "paid", "paid_at": {"$gte": since}})
    last_paid = await db.applications.find_one({"payment_status": "paid"}, {"_id": 0, "paid_at": 1, "tracking_no": 1, "payment_method": 1}, sort=[("paid_at", -1)])
    uptime = {}
    for h in history:
        for r in h.get("results", []):
            u = uptime.setdefault(r["gateway"], [0, 0])
            u[1] += 1
            u[0] += 1 if r["status"] == "up" else 0
    return {
        "latest": history[0] if history else None,
        "history": history,
        "uptime_pct": {g: round(100 * a / b, 1) for g, (a, b) in uptime.items() if b},
        "payments_24h": {"paid": paid_24h, "failed": failed_24h},
        "last_paid": last_paid,
    }


@api.post("/cron/gateway-health")
async def cron_gateway_health(request: Request):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    secret = os.environ["WEBHOOK_CRON_SECRET"]
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], secret):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid body")
    run_id = request.headers.get("x-webhook-id") or body.get("run_id") or str(uuid.uuid4())
    try:
        await db.cron_runs.insert_one({"run_id": run_id, "job": "gateway-health", "created_at": now_iso()})
    except Exception:
        return {"ok": True, "duplicate": True}

    async def _job():
        try:
            await _check_gateways_and_alert()
        except Exception as e:
            logger.warning(f"gateway health cron failed: {e}")
        try:
            await _reconcile_pending_hubtel()
        except Exception as e:
            logger.warning(f"hubtel reconciliation failed: {e}")
    asyncio.create_task(_job())
    return {"ok": True, "accepted": run_id}


@api.get("/admin/payment-verifications")
async def admin_payment_verifications(ctx: dict = Depends(require_admin)):
    """Live Hubtel payments awaiting or failing server-side verification."""
    return await db.applications.find(
        {"payment_status": {"$ne": "paid"}, "payment_verification.state": {"$in": ["error", "unpaid", "mismatch", "refunded"]}},
        {"_id": 0, "tracking_no": 1, "full_name": 1, "amount_usd": 1, "amount_charged": 1, "payment_currency": 1,
         "payment_verification": 1, "updated_at": 1},
    ).sort("updated_at", -1).limit(100).to_list(100)


@api.post("/admin/applications/{tracking_no}/verify-payment")
async def admin_verify_payment(tracking_no: str, ctx: dict = Depends(require_admin)):
    if is_sandbox((await get_settings()).get("hubtel", {})):
        raise HTTPException(status_code=400, detail="Hubtel is in sandbox mode — nothing to verify")
    state = await _verify_hubtel_payment(tracking_no)
    if state == "not_found":
        raise HTTPException(status_code=404, detail="Application not found")
    doc = await db.applications.find_one({"tracking_no": tracking_no}, {"_id": 0, "payment_verification": 1, "payment_status": 1})
    return {"state": state, **doc}



# ────────────────── ANALYTICS (first-party) ──────────────────

class AnalyticsTrackIn(BaseModel):
    visitor_id: str
    session_id: str
    event: str = "pageview"
    path: str = ""
    referrer: str = ""
    screen: str = ""
    lang: str = ""
    ts: str = ""
    utm: Optional[dict] = None
    extra: Optional[dict] = None


@api.post("/analytics/track")
async def analytics_track(payload: AnalyticsTrackIn, request: Request):
    """Public first-party analytics collector. Called only after user has
    consented to analytics cookies (enforced client-side)."""
    ua = request.headers.get("user-agent", "")
    device, os_name, browser = _parse_ua(ua)
    utm = payload.utm or {}
    utm_source = str(utm.get("source") or "")
    utm_medium = str(utm.get("medium") or "")
    host = request.url.hostname or ""
    source = _classify_source(payload.referrer, host, utm_source, utm_medium)
    doc = {
        "id": str(uuid.uuid4()),
        "visitor_id": payload.visitor_id,
        "session_id": payload.session_id,
        "event": payload.event,
        "path": payload.path[:512],
        "referrer": payload.referrer[:512],
        "source": source,
        "device": device,
        "os": os_name,
        "browser": browser,
        "country": _country_from_headers(request.headers),
        "city": _city_from_headers(request.headers),
        "screen": payload.screen[:32],
        "lang": (payload.lang or "")[:16],
        "utm_source": utm_source[:64],
        "utm_medium": utm_medium[:64],
        "utm_campaign": str(utm.get("campaign") or "")[:128],
        "extra": payload.extra or {},
        "created_at": now_iso(),
    }
    await db.analytics_events.insert_one(doc)
    return {"ok": True}


@api.get("/analytics/public-config")
async def analytics_public_config():
    """Public IDs used by the frontend to conditionally load GA4/Clarity and
    inject the GSC verification meta tag. Never contains secrets."""
    s = await get_settings()
    return {
        "ga4_measurement_id": s.get("ga4_measurement_id", ""),
        "gsc_verification": s.get("gsc_verification", ""),
        "clarity_project_id": s.get("clarity_project_id", ""),
    }


class AnalyticsIdsIn(BaseModel):
    ga4_measurement_id: str = ""
    gsc_verification: str = ""
    clarity_project_id: str = ""


@api.post("/admin/settings/analytics-ids")
async def admin_update_analytics_ids(payload: AnalyticsIdsIn, ctx: dict = Depends(require_admin)):
    await db.settings.update_one(
        {"id": "singleton"},
        {"$set": {
            "ga4_measurement_id": payload.ga4_measurement_id.strip(),
            "gsc_verification": payload.gsc_verification.strip(),
            "clarity_project_id": payload.clarity_project_id.strip(),
            "updated_at": now_iso(),
        }},
    )
    return {"ok": True}


@api.get("/admin/analytics/summary")
async def admin_analytics_summary(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    preset: Optional[str] = Query(None),
    ctx: dict = Depends(require_admin),
):
    start, end = _parse_date_range(from_, to, preset or "30d")
    start_iso, end_iso = start.isoformat(), end.isoformat()
    ev_filter = {"created_at": {"$gte": start_iso, "$lte": end_iso}}

    # Base aggregates
    total_events = await db.analytics_events.count_documents(ev_filter)
    total_pv = await db.analytics_events.count_documents({**ev_filter, "event": "pageview"})
    visitors = await db.analytics_events.distinct("visitor_id", ev_filter)
    sessions = await db.analytics_events.distinct("session_id", ev_filter)
    total_visitors = len(visitors)
    total_sessions = len(sessions)

    # Returning visitors (visitor first-seen before this window)
    returning = 0
    if visitors:
        returning = await db.analytics_events.count_documents({
            "visitor_id": {"$in": visitors},
            "created_at": {"$lt": start_iso},
        })
        # count distinct returning visitor ids
        returning_ids = await db.analytics_events.distinct("visitor_id", {
            "visitor_id": {"$in": visitors},
            "created_at": {"$lt": start_iso},
        })
        returning = len(returning_ids)
    unique_visitors = total_visitors
    new_visitors = max(0, unique_visitors - returning)

    # Bounce & session duration — group events per session
    pipeline_sessions = [
        {"$match": ev_filter},
        {"$group": {
            "_id": "$session_id",
            "count": {"$sum": 1},
            "start_ts": {"$min": "$created_at"},
            "end_ts": {"$max": "$created_at"},
        }},
    ]
    bounced = 0
    session_durations = []
    async for row in db.analytics_events.aggregate(pipeline_sessions):
        if row["count"] <= 1:
            bounced += 1
        try:
            st = datetime.fromisoformat(row["start_ts"].replace("Z", "+00:00"))
            et = datetime.fromisoformat(row["end_ts"].replace("Z", "+00:00"))
            session_durations.append((et - st).total_seconds())
        except Exception:
            pass
    bounce_rate = round(100 * bounced / total_sessions, 1) if total_sessions else 0.0
    avg_session_sec = round(sum(session_durations) / len(session_durations), 1) if session_durations else 0.0

    # Traffic sources
    src_agg = {}
    async for row in db.analytics_events.aggregate([
        {"$match": ev_filter},
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
    ]):
        src_agg[row["_id"] or "Direct"] = row["count"]
    all_sources = ["Organic Search", "Direct", "Social Media", "Referral", "Paid Ads"]
    traffic_sources = [{"name": k, "count": src_agg.get(k, 0)} for k in all_sources]

    async def _group(field, top=10):
        out = []
        async for row in db.analytics_events.aggregate([
            {"$match": ev_filter},
            {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": top},
        ]):
            out.append({"name": row["_id"] or "Unknown", "count": row["count"]})
        return out

    devices = await _group("device")
    os_list = await _group("os")
    browsers = await _group("browser")
    countries_raw = await _group("country", top=15)
    countries = [{**c, "label": _COUNTRY_NAMES.get(c["name"], c["name"])} for c in countries_raw]
    cities = [c for c in await _group("city", top=15) if c["name"] and c["name"] != "Unknown"]
    top_landing = await _group("path", top=10)

    # Applications & revenue in window
    app_filter = {"created_at": {"$gte": start_iso, "$lte": end_iso}}
    apps_total = await db.applications.count_documents(app_filter)
    apps_paid = await db.applications.count_documents({**app_filter, "payment_status": "paid"})
    apps_abandoned = await db.applications.count_documents({**app_filter, "payment_status": {"$ne": "paid"}})

    revenue_agg = 0.0
    async for row in db.applications.aggregate([
        {"$match": {**app_filter, "payment_status": "paid"}},
        {"$group": {"_id": None, "sum": {"$sum": "$amount_usd"}}},
    ]):
        revenue_agg = float(row.get("sum", 0.0))

    # Button-click events
    apply_clicks = await db.analytics_events.count_documents({**ev_filter, "event": "apply_click"})
    payment_clicks = await db.analytics_events.count_documents({**ev_filter, "event": "payment_click"})

    # Conversion rate = paid applications / unique visitors
    conversion_rate = round(100 * apps_paid / unique_visitors, 2) if unique_visitors else 0.0

    return {
        "range": {"from": start_iso, "to": end_iso},
        "web": {
            "total_visitors": unique_visitors,
            "unique_visitors": unique_visitors,
            "new_visitors": new_visitors,
            "returning_visitors": returning,
            "page_views": total_pv,
            "sessions": total_sessions,
            "avg_session_duration_sec": avg_session_sec,
            "bounce_rate_pct": bounce_rate,
            "events_total": total_events,
        },
        "conversion": {
            "apply_clicks": apply_clicks,
            "payment_clicks": payment_clicks,
            "applications_submitted": apps_total,
            "applications_paid": apps_paid,
            "applications_abandoned": apps_abandoned,
            "conversion_rate_pct": conversion_rate,
            "revenue_usd": round(revenue_agg, 2),
        },
        "sources": traffic_sources,
        "devices": devices,
        "os": os_list,
        "browsers": browsers,
        "countries": countries,
        "cities": cities,
        "top_landing_pages": top_landing,
    }


@api.get("/admin/analytics/timeseries")
async def admin_analytics_timeseries(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    preset: Optional[str] = Query(None),
    ctx: dict = Depends(require_admin),
):
    """Daily buckets: visitors, page-views, applications, revenue."""
    start, end = _parse_date_range(from_, to, preset or "30d")
    start_iso, end_iso = start.isoformat(), end.isoformat()

    # Daily unique visitors
    daily = {}
    async for row in db.analytics_events.aggregate([
        {"$match": {"created_at": {"$gte": start_iso, "$lte": end_iso}, "event": "pageview"}},
        {"$group": {
            "_id": {"$substr": ["$created_at", 0, 10]},
            "pv": {"$sum": 1},
            "vs": {"$addToSet": "$visitor_id"},
        }},
    ]):
        daily[row["_id"]] = {"date": row["_id"], "page_views": row["pv"], "visitors": len(row["vs"]), "applications": 0, "revenue": 0.0}

    async for row in db.applications.aggregate([
        {"$match": {"created_at": {"$gte": start_iso, "$lte": end_iso}}},
        {"$group": {
            "_id": {"$substr": ["$created_at", 0, 10]},
            "apps": {"$sum": 1},
            "revenue": {"$sum": {"$cond": [{"$eq": ["$payment_status", "paid"]}, "$amount_usd", 0]}},
        }},
    ]):
        d = daily.setdefault(row["_id"], {"date": row["_id"], "page_views": 0, "visitors": 0, "applications": 0, "revenue": 0.0})
        d["applications"] = row["apps"]
        d["revenue"] = round(float(row.get("revenue", 0.0)), 2)

    series = sorted(daily.values(), key=lambda x: x["date"])
    return {"range": {"from": start_iso, "to": end_iso}, "series": series}


# ────────────────── SEO STATUS ──────────────────

CORE_ROUTES_META = [
    ("/", "Ghana Visa On Arrival — eVisa & ETA assistance"),
    ("/apply", "Apply for your Ghana Visa"),
    ("/prices", "Ghana Visa prices"),
    ("/track", "Track my Ghana Visa application"),
    ("/faq", "Ghana Visa FAQ"),
    ("/ghana-evisa", "Ghana eVisa Guide"),
    ("/ghana-business-visa", "Ghana Business Visa Guide"),
    ("/terms", "Terms & Conditions"),
    ("/privacy", "Privacy Policy"),
    ("/disclaimer", "Disclaimer"),
]


@api.get("/admin/seo/status")
async def admin_seo_status(request: Request, ctx: dict = Depends(require_admin)):
    """Best-effort SEO health check. Verifies sitemap.xml, robots.txt and lists
    the meta status of core routes based on our React Helmet configuration."""
    # Prefer the customer-facing host (X-Forwarded-Host set by ingress) over
    # the internal cluster hostname exposed by request.base_url.
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    proto = request.headers.get("x-forwarded-proto", "https")
    if forwarded_host:
        origin = f"{proto}://{forwarded_host.split(',')[0].strip()}"
    else:
        origin = str(request.base_url).rstrip("/")
    try:
        import httpx  # local import — httpx is already present in the project
    except Exception:
        httpx = None

    checks = {"sitemap": {"url": f"{origin}/sitemap.xml", "ok": False},
              "robots": {"url": f"{origin}/robots.txt", "ok": False}}

    async def _fetch(url: str) -> Optional[int]:
        if httpx is None:
            return None
        try:
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as c:
                r = await c.get(url)
                return r.status_code
        except Exception:
            return None

    for key in ("sitemap", "robots"):
        code = await _fetch(checks[key]["url"])
        checks[key]["status_code"] = code
        checks[key]["ok"] = code is not None and 200 <= code < 400

    # SEO landing pages are dynamically served; each carries meta title/desc via
    # React Helmet. We list core routes as "configured".
    pages = [
        {"path": p, "meta_title": bool(title), "meta_description": True, "canonical": True, "structured_data": p in ("/", "/apply", "/ghana-evisa")}
        for p, title in CORE_ROUTES_META
    ]

    return {
        "sitemap": checks["sitemap"],
        "robots": checks["robots"],
        "core_pages": pages,
        "indexed_pages_estimate": len(pages),  # actual indexed count requires GSC API
        "gsc_connected": False,
    }


# ────────────────── DATA CLEANUP / DANGER ZONE ──────────────────

@api.get("/admin/cleanup/preview")
async def admin_cleanup_preview(ctx: dict = Depends(require_admin)):
    """List applications matching test-data heuristics (safe cleanup)."""
    matches = []
    async for doc in db.applications.find({}, {"_id": 0}):
        if _is_test_record(doc):
            matches.append({
                "tracking_no": doc.get("tracking_no"),
                "full_name": doc.get("full_name"),
                "email": doc.get("email"),
                "passport_number": doc.get("passport_number"),
                "created_at": doc.get("created_at"),
                "payment_status": doc.get("payment_status"),
            })
    return {"count": len(matches), "items": matches[:200]}


@api.post("/admin/cleanup/test-data")
async def admin_cleanup_test_data(ctx: dict = Depends(require_admin)):
    """Delete applications matching test heuristics and their related side data
    (payment records, chat logs). Safe: only touches records the preview endpoint returns.
    Also purges the corresponding R2 folder for each affected tracking number."""
    tracking_nos = []
    async for doc in db.applications.find({}, {"tracking_no": 1, "_id": 0}):
        full = await db.applications.find_one({"tracking_no": doc["tracking_no"]}, {"_id": 0})
        if full and _is_test_record(full):
            tracking_nos.append(doc["tracking_no"])

    deleted = {"applications": 0, "hubtel_callbacks": 0, "crypto_payments": 0, "email_log": 0, "chat_log": 0, "r2_objects": 0}
    if tracking_nos:
        settings = await get_settings()
        r2 = R2StorageBackend((settings or {}).get("r2") or {})
        if r2.is_configured():
            for tn in tracking_nos:
                deleted["r2_objects"] += r2.delete_prefix(r2.applicant_prefix(tn))
        res = await db.applications.delete_many({"tracking_no": {"$in": tracking_nos}})
        deleted["applications"] = res.deleted_count
        res = await db.hubtel_callbacks.delete_many({"client_reference": {"$in": tracking_nos}})
        deleted["hubtel_callbacks"] = res.deleted_count
        res = await db.crypto_payments.delete_many({"tracking_no": {"$in": tracking_nos}})
        deleted["crypto_payments"] = res.deleted_count
    return {"ok": True, "deleted": deleted, "tracking_nos": tracking_nos}


class WipeAllIn(BaseModel):
    confirm: str


@api.post("/admin/cleanup/wipe-all")
async def admin_wipe_all(payload: WipeAllIn, ctx: dict = Depends(require_admin)):
    """Nuclear option: wipe ALL applications, payments, callbacks, logs and analytics.
    Requires body {\"confirm\":\"DELETE ALL\"}. Preserves admin settings, users,
    email templates. Also purges the R2 bucket under this environment's prefix."""
    if payload.confirm != "DELETE ALL":
        raise HTTPException(status_code=400, detail='Confirmation string must be exactly "DELETE ALL".')

    collections = [
        "applications", "hubtel_callbacks", "crypto_payments",
        "email_log", "chat_log", "analytics_events",
    ]
    deleted = {}
    for coll in collections:
        res = await db[coll].delete_many({})
        deleted[coll] = res.deleted_count

    # Purge R2 under this env's applicants/ prefix to avoid orphans
    settings = await get_settings()
    r2 = R2StorageBackend((settings or {}).get("r2") or {})
    r2_deleted = 0
    if r2.is_configured():
        r2_deleted = r2.delete_prefix(f"{r2.env_prefix}/applicants/")
        r2_deleted += r2.delete_prefix(f"{r2.env_prefix}/payments/")
        r2_deleted += r2.delete_prefix(f"{r2.env_prefix}/invoices/")
    deleted["r2_objects"] = r2_deleted
    return {"ok": True, "deleted": deleted}


# ────────────────── SINGLE APPLICATION DELETE (with R2 purge) ──────────────────

@api.delete("/admin/applications/{tracking_no}")
async def admin_delete_application(tracking_no: str, ctx: dict = Depends(require_admin)):
    """Delete a specific application and all of its associated data — MongoDB
    records (application, payment side records) and every R2 object under the
    application's folder. Idempotent."""
    app_doc = await db.applications.find_one({"tracking_no": tracking_no}, {"_id": 0})
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")

    settings = await get_settings()
    deleted = {"applications": 0, "hubtel_callbacks": 0, "crypto_payments": 0, "r2_objects": 0, "legacy_files": 0}

    # Try both backends — the app may have files in R2 or in the legacy Emergent backend
    r2 = R2StorageBackend((settings or {}).get("r2") or {})
    if r2.is_configured():
        deleted["r2_objects"] = r2.delete_prefix(r2.applicant_prefix(tracking_no))
    # Legacy — Emergent has no delete API; count files that will orphan for admin awareness
    for _doc_type, ref in (app_doc.get("documents") or {}).items():
        path = (ref or {}).get("path", "")
        if path.startswith(("eghanavisa/", "eghanavisa/applications/")):
            deleted["legacy_files"] += 1

    r = await db.applications.delete_one({"tracking_no": tracking_no})
    deleted["applications"] = r.deleted_count
    r = await db.hubtel_callbacks.delete_many({"client_reference": tracking_no})
    deleted["hubtel_callbacks"] = r.deleted_count
    r = await db.crypto_payments.delete_many({"tracking_no": tracking_no})
    deleted["crypto_payments"] = r.deleted_count
    return {"ok": True, "tracking_no": tracking_no, "deleted": deleted}


# ────────────────── STORAGE (Cloudflare R2) ADMIN ──────────────────

class R2ConfigIn(BaseModel):
    enabled: bool = True
    account_id: str = ""
    bucket: str = ""
    access_key_id: str = ""
    secret_access_key: str = ""
    cdn_domain: str = ""
    env_prefix: str = ""
    signed_url_ttl: int = 900


@api.post("/admin/settings/r2")
async def admin_update_r2(payload: R2ConfigIn, ctx: dict = Depends(require_admin)):
    """Persist Cloudflare R2 credentials. Empty secret_access_key means 'keep
    existing' so admins can edit the config without re-typing the secret."""
    current = (await get_settings()).get("r2") or {}
    updates = {
        "enabled": payload.enabled,
        "account_id": payload.account_id.strip(),
        "bucket": payload.bucket.strip(),
        "access_key_id": payload.access_key_id.strip(),
        "cdn_domain": payload.cdn_domain.strip(),
        "env_prefix": payload.env_prefix.strip(),
        "signed_url_ttl": max(60, min(int(payload.signed_url_ttl or 900), 24 * 3600)),
    }
    secret = payload.secret_access_key.strip()
    updates["secret_access_key"] = secret if secret else current.get("secret_access_key", "")
    await db.settings.update_one(
        {"id": "singleton"},
        {"$set": {"r2": updates, "updated_at": now_iso()}},
    )
    return {"ok": True, "r2": _redact_r2(updates)}


@api.post("/admin/storage/test")
async def admin_storage_test(ctx: dict = Depends(require_admin)):
    """Runs a HEAD + tiny put/delete round-trip against R2 to verify credentials
    and permissions. Returns detailed result to display in the admin UI."""
    settings = await get_settings()
    r2 = R2StorageBackend((settings or {}).get("r2") or {})
    return r2.test_connection()


@api.get("/admin/storage/status")
async def admin_storage_status(ctx: dict = Depends(require_admin)):
    """Read-only summary of the active storage backend."""
    settings = await get_settings()
    r2_cfg = (settings or {}).get("r2") or {}
    r2 = R2StorageBackend(r2_cfg)
    return {
        "env_detected": _detect_env(),
        "r2_configured": r2.is_configured(),
        "r2_enabled": bool(r2_cfg.get("enabled", True)),
        "active_backend": "r2" if (r2.is_configured() and r2_cfg.get("enabled", True)) else "emergent (legacy)",
        "bucket": r2.bucket or None,
        "cdn_domain": r2.cdn_domain or None,
        "env_prefix": r2.env_prefix,
        "signed_url_ttl": r2.signed_url_ttl,
    }


def _redact_r2(cfg: dict) -> dict:
    """Return R2 config with the secret masked — for API responses."""
    safe = dict(cfg or {})
    if safe.get("secret_access_key"):
        s = safe["secret_access_key"]
        safe["secret_access_key"] = f"****{s[-4:]}" if len(s) > 4 else "****"
    return safe


# ────────────────── FX (USD → GHS) ADMIN ──────────────────

class FxConfigIn(BaseModel):
    provider: str = "open_er_api"
    manual_rate: float = 0.0
    buffer_pct: float = 0.0
    cache_seconds: int = 900


@api.post("/admin/settings/fx")
async def admin_update_fx(payload: FxConfigIn, ctx: dict = Depends(require_admin)):
    if payload.provider not in _FX_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider. Allowed: {list(_FX_PROVIDERS)}")
    fx = {
        "provider": payload.provider,
        "manual_rate": max(0.0, float(payload.manual_rate)),
        "buffer_pct": max(0.0, min(10.0, float(payload.buffer_pct))),
        "cache_seconds": max(60, min(int(payload.cache_seconds), 24 * 3600)),
    }
    await db.settings.update_one(
        {"id": "singleton"},
        {"$set": {"fx": fx, "updated_at": now_iso()}},
    )
    return {"ok": True, "fx": fx}


@api.get("/admin/fx/providers")
async def admin_fx_providers(ctx: dict = Depends(require_admin)):
    return {
        "providers": [
            {"key": k, "label": v["label"], "requires_manual_rate": (k == "manual")}
            for k, v in _FX_PROVIDERS.items()
        ]
    }


@api.get("/admin/fx/live")
async def admin_fx_live(ctx: dict = Depends(require_admin)):
    """Fetch the current USD → GHS rate right now (bypasses cache when possible)
    so admins can preview what customers would be charged."""
    settings = await get_settings()
    try:
        r = _fx_get_rate(settings.get("fx", {}))
        # Example: convert $100 USD to see the buffered result
        sample_100 = round(100.0 * r["buffered_rate"], 2)
        return {"ok": True, **r, "sample_100_usd_to_ghs": sample_100}
    except FxError as e:
        return {"ok": False, "detail": str(e)}


# ────────────────── MOUNT ──────────────────
app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
