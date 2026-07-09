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
from pathlib import Path
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime, timezone

from countries import passport_countries, travel_from_countries
from auth_utils import hash_password, verify_password, create_token, require_admin
from storage_service import storage, validate_file, MIME_MAP
from email_service import EmailService
from hubtel_service import initiate_checkout, is_sandbox
from ama_chat import ask_ama
import nowpayments_service as nowp
from seed_data import DEFAULT_SETTINGS, DEFAULT_EMAIL_TEMPLATES, EMAIL_TEMPLATES_VERSION, OBSOLETE_VISA_CODES

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


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def _notify_admin(template_name: str, context: dict) -> None:
    """Fire-and-forget internal ops email. Never breaks the caller if email fails."""
    try:
        s = await get_settings()
        recipient = (s.get("admin_notification_email") or "").strip()
        if not recipient:
            return
        await email_svc.send(
            recipient=recipient,
            template_name=template_name,
            lang="en",
            context=context,
        )
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
    return {
        "visa_types": s.get("visa_types", []),
        "payment_methods": s.get("payment_methods", []),
        "express_surcharge_usd": s.get("express_surcharge_usd", 50.0),
        "max_upload_mb": s.get("max_upload_mb", 8),
        "whatsapp_admin": s.get("whatsapp_admin", ""),
        "hubtel_sandbox": is_sandbox(s.get("hubtel", {})),
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

    path = storage.build_path(tracking_no, doc_type, ext)
    result = storage.put(path, data, MIME_MAP.get(ext, "application/octet-stream"))

    await db.applications.update_one(
        {"tracking_no": tracking_no},
        {"$set": {
            f"documents.{doc_type}": {
                "path": result["path"],
                "original_filename": file.filename,
                "content_type": MIME_MAP.get(ext),
                "size": result.get("size", len(data)),
                "uploaded_at": now_iso(),
            },
            "updated_at": now_iso(),
        }},
    )
    return {"ok": True, "doc_type": doc_type, "path": result["path"]}


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
    result = initiate_checkout(
        settings.get("hubtel", {}),
        amount=app_doc["amount_usd"],
        description=f"Ghana Visa {app_doc['visa_name']} - {app_doc['tracking_no']}",
        tracking_no=app_doc["tracking_no"],
    )
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
async def admin_applications(status: str = Query("all"), ctx: dict = Depends(require_admin)):
    q = {"payment_status": "paid"}
    if status in ("submitted", "in_progress", "done"):
        q["status"] = status
    docs = await db.applications.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return docs


@api.get("/admin/applications/{tracking_no}")
async def admin_application_detail(tracking_no: str, ctx: dict = Depends(require_admin)):
    doc = await db.applications.find_one({"tracking_no": tracking_no}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return doc


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
    data, ct = storage.get(ref["path"])
    return Response(content=data, media_type=ref.get("content_type", ct))


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
    return await get_settings()


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


# ────────────────── AMA CHAT ──────────────────
class ChatIn(BaseModel):
    message: str
    session_id: Optional[str] = None


@api.post("/chat")
async def chat_endpoint(payload: ChatIn):
    s = await get_settings()
    session_id = payload.session_id or str(uuid.uuid4())
    reply = await ask_ama(
        message=payload.message,
        session_id=session_id,
        whatsapp=s.get("whatsapp_admin", ""),
        model=s.get("ai_model", "claude-sonnet-4-5-20250929"),
    )
    await db.chat_log.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "user_message": payload.message,
        "ai_reply": reply,
        "created_at": now_iso(),
    })
    return {"reply": reply, "session_id": session_id, "whatsapp": s.get("whatsapp_admin", "")}


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
