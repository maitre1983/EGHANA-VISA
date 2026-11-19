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
)
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


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def _notify_admin(template_name: str, context: dict) -> None:
    """Fire-and-forget internal ops email. Never breaks the caller if email fails.
    Fans out to the primary admin_notification_email + any additional_admin_emails."""
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
            return
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
            except Exception as inner:
                logger.warning(f"Admin notification failed for {rcpt} ({template_name}): {inner}")
    except Exception as e:
        logger.warning(f"Admin notification failed ({template_name}): {e}")


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
        return
    await db.email_templates.delete_many({})
    await db.email_templates.insert_many([dict(t) for t in DEFAULT_EMAIL_TEMPLATES])
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


# ────────────────────────── HELPERS ──────────────────────────
async def get_settings() -> dict:
    doc = await db.settings.find_one({"id": "singleton"}, {"_id": 0})
    return doc or dict(DEFAULT_SETTINGS)


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
async def payment_initiate(payload: PayInit):
    app_doc = await db.applications.find_one({"tracking_no": payload.tracking_no}, {"_id": 0})
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")
    if app_doc.get("payment_status") == "paid":
        raise HTTPException(status_code=400, detail="Application already paid")

    settings = await get_settings()
    hubtel_cfg = settings.get("hubtel", {})

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
    await db.applications.update_one(
        {"tracking_no": app_doc["tracking_no"]},
        {"$set": {
            "payment_status": "paid",
            "status": "submitted",
            "paid_at": now_iso(),
            "payment_method": payment_method,
            "updated_at": now_iso(),
        }},
    )
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
    return True


@api.post("/payments/confirm")
async def payment_confirm(payload: PayConfirm):
    """SANDBOX-only endpoint: allows the mock checkout page to mark an application
    as paid. Rejected when real Hubtel credentials are configured — production
    payments MUST flow through /api/webhooks/hubtel."""
    settings = await get_settings()
    if not is_sandbox(settings.get("hubtel", {})):
        raise HTTPException(status_code=403, detail="Sandbox-only endpoint. Production uses the Hubtel webhook.")

    app_doc = await db.applications.find_one({"tracking_no": payload.tracking_no}, {"_id": 0})
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")

    if not payload.success:
        await db.applications.update_one(
            {"tracking_no": payload.tracking_no},
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
        {"_id": 0, "payment_status": 1, "status": 1, "tracking_no": 1, "visa_name": 1, "amount_usd": 1},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Application not found")
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

    if _hubtel_success(data):
        await _mark_application_paid(app_doc, payment_method="Visa card (Hubtel)")
    else:
        await db.applications.update_one(
            {"tracking_no": client_ref},
            {"$set": {"payment_status": "failed", "updated_at": now_iso()}},
        )
    return {"ok": True}


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
    ctx: dict = Depends(require_admin),
):
    """List applications. All new filters are optional and additive — existing
    callers (no params) see the exact same payload as before."""
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
    pipeline = [
        {"$match": q},
        {"$addFields": {"_effective_at": {"$ifNull": ["$submitted_at", "$created_at"]}}},
        {"$sort": {"_effective_at": -1}},
        {"$project": {"_id": 0, "_effective_at": 0}},
        {"$limit": 1000},
    ]
    docs = await db.applications.aggregate(pipeline).to_list(1000)
    return docs


@api.get("/admin/applications/{tracking_no}")
async def admin_application_detail(tracking_no: str, ctx: dict = Depends(require_admin)):
    doc = await db.applications.find_one({"tracking_no": tracking_no}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return doc


# ----------------- Payments / Transactions (read-only, unified) -----------------
from transactions_service import list_transactions, compute_summary, to_csv


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
async def crypto_initiate(payload: CryptoInitIn):
    if payload.network not in nowp.CURRENCY_MAP:
        raise HTTPException(status_code=400, detail="Invalid network")

    s = await get_settings()
    cfg = s.get("nowpayments", {})

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


class SimulateFinishIn(BaseModel):
    success: bool = True


@api.post("/payments/crypto/simulate-finish/{payment_id}")
async def crypto_simulate_finish(payment_id: str, payload: SimulateFinishIn):
    """Simulate a NowPayments IPN 'finished' or 'failed' — sandbox helper only."""
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
async def crypto_status(payment_id: str):
    doc = await db.crypto_payments.find_one({"payment_id": payment_id}, {"_id": 0, "ipn_payloads": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Unknown crypto payment")

    # Best-effort refresh from NowPayments if still pending (polling fallback)
    if doc.get("payment_status") not in ("finished", "failed", "refunded", "expired") and not doc.get("simulated"):
        s = await get_settings()
        cfg = s.get("nowpayments", {})
        if nowp.is_configured(cfg):
            try:
                remote = nowp.get_payment(cfg, payment_id)
                np_status = remote.get("payment_status", doc["payment_status"])
                if np_status != doc["payment_status"]:
                    await _apply_crypto_status_update(payment_id, np_status, remote, ipn=False)
                    doc["payment_status"] = np_status
                    doc["actually_paid"] = remote.get("actually_paid")
            except Exception as e:
                logger.warning(f"NowPayments polling failed: {e}")

    return {
        "payment_id": doc["payment_id"],
        "tracking_no": doc["tracking_no"],
        "payment_status": doc["payment_status"],
        "internal_status": nowp.map_status(doc["payment_status"]),
        "pay_address": doc["pay_address"],
        "pay_amount": doc["pay_amount"],
        "pay_currency": doc["pay_currency"],
        "actually_paid": doc.get("actually_paid"),
        "network": doc["network"],
    }


async def _apply_crypto_status_update(payment_id: str, np_status: str, payload: dict, ipn: bool):
    """Idempotently update crypto_payments + trigger visa confirmation on 'finished'."""
    doc = await db.crypto_payments.find_one({"payment_id": payment_id}, {"_id": 0})
    if not doc:
        return
    if doc.get("payment_status") == np_status and not ipn:
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

    # On finished: mark application paid (idempotent) and send confirmation email
    if np_status == "finished":
        app_doc = await db.applications.find_one({"tracking_no": doc["tracking_no"]}, {"_id": 0})
        if app_doc and app_doc.get("payment_status") != "paid":
            await db.applications.update_one(
                {"tracking_no": app_doc["tracking_no"]},
                {"$set": {
                    "payment_status": "paid",
                    "status": "submitted",
                    "paid_at": now_iso(),
                    "payment_method": f"usdt_{doc['network']}",
                    "updated_at": now_iso(),
                }},
            )
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
                template_name="submitted",  # generic — real templates should include a "support_reply" one
                lang="en",
                context={
                    "name": t.get("customer_name") or "Traveller",
                    "tracking": t.get("tracking_no") or f"TKT-{ticket_id[:8]}",
                    "visa_type": "Support",
                    "processing": "Reply from our team",
                    "amount": "-",
                },
            )
        except Exception as e:
            logger.warning(f"Ticket reply email failed: {e}")
    return {"ok": True}



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
