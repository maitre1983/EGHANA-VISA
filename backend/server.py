"""e.GHANA Visa Portal — FastAPI backend."""
from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form, Depends, Response, Query
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
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
from seed_data import DEFAULT_SETTINGS, DEFAULT_EMAIL_TEMPLATES

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


# ────────────────────────── STARTUP ──────────────────────────
@app.on_event("startup")
async def startup():
    # Seed default admin
    admin_email = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@eghanavisa.com")
    admin_pass = os.environ.get("DEFAULT_ADMIN_PASSWORD", "Admin@2026")
    existing = await db.admins.find_one({"email": admin_email}, {"_id": 0})
    if not existing:
        await db.admins.insert_one({
            "id": str(uuid.uuid4()),
            "email": admin_email,
            "password_hash": hash_password(admin_pass),
            "must_change_password": True,
            "created_at": now_iso(),
        })
        logger.info(f"Seeded default admin: {admin_email}")

    # Seed settings
    existing_settings = await db.settings.find_one({"id": "singleton"}, {"_id": 0})
    if not existing_settings:
        await db.settings.insert_one(dict(DEFAULT_SETTINGS))
        logger.info("Seeded default settings")

    # Seed email templates
    if await db.email_templates.count_documents({}) == 0:
        await db.email_templates.insert_many([dict(t) for t in DEFAULT_EMAIL_TEMPLATES])
        logger.info("Seeded default email templates")


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
    return {
        "visa_types": s.get("visa_types", []),
        "payment_methods": s.get("payment_methods", []),
        "express_surcharge_usd": s.get("express_surcharge_usd", 50.0),
        "max_upload_mb": s.get("max_upload_mb", 8),
        "whatsapp_admin": s.get("whatsapp_admin", ""),
        "hubtel_sandbox": is_sandbox(s.get("hubtel", {})),
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
    processing: str  # 'regular' | 'express'
    lang: str = "en"


@api.post("/applications")
async def create_application(payload: ApplicationIn):
    settings = await get_settings()
    price, visa = visa_price(settings, payload.visa_code)
    if not visa.get("active"):
        raise HTTPException(status_code=400, detail="Visa type is not currently available")

    processing = payload.processing.lower()
    if processing not in ("regular", "express"):
        raise HTTPException(status_code=400, detail="Invalid processing type")

    surcharge = float(settings.get("express_surcharge_usd", 50.0)) if processing == "express" else 0.0
    total = price + surcharge

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


@api.post("/payments/confirm")
async def payment_confirm(payload: PayConfirm):
    """Called by the sandbox UI or by Hubtel callback proxy (simplified).
    In production this endpoint should verify the transaction via Hubtel Status API."""
    app_doc = await db.applications.find_one({"tracking_no": payload.tracking_no}, {"_id": 0})
    if not app_doc:
        raise HTTPException(status_code=404, detail="Application not found")

    if not payload.success:
        await db.applications.update_one(
            {"tracking_no": payload.tracking_no},
            {"$set": {"payment_status": "failed", "updated_at": now_iso()}},
        )
        return {"ok": False}

    await db.applications.update_one(
        {"tracking_no": payload.tracking_no},
        {"$set": {
            "payment_status": "paid",
            "status": "submitted",
            "paid_at": now_iso(),
            "updated_at": now_iso(),
        }},
    )
    # Email
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
    return {"ok": True, "tracking_no": payload.tracking_no}


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
