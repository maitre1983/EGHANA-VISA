"""Default seed values for settings and email templates."""
from datetime import datetime, timezone
from typing import List, Dict, Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_VISA_TYPES: List[Dict[str, Any]] = [
    {"code": "tourist_30", "name_en": "30 Days Tourist Visa", "name_fr": "Visa touristique 30 jours", "days": 30, "price_usd": 350.0, "active": True, "always_active": True, "express_available": True, "processing_time_label": "5–7 business days", "requires_presence": False},
    {"code": "extended_60", "name_en": "60 Days Extended Visa", "name_fr": "Visa étendu 60 jours", "days": 60, "price_usd": 500.0, "active": False, "always_active": False, "express_available": True, "processing_time_label": "5–7 business days", "requires_presence": False},
    {"code": "residence_1y", "name_en": "1 Year Residence Permit", "name_fr": "Permis de résidence 1 an", "days": 365, "price_usd": 1200.0, "active": False, "always_active": False, "express_available": False, "processing_time_label": "45–60 days · in-country presence required", "requires_presence": True},
]

DEFAULT_PAYMENT_METHODS: List[Dict[str, Any]] = [
    {"code": "hubtel_visa", "name": "Visa Card via Hubtel", "active": True, "always_active": False},
    {"code": "usdt_trc20", "name": "USDT (TRC20)", "active": False, "always_active": False},
    {"code": "usdt_bep20", "name": "USDT (BEP20)", "active": False, "always_active": False},
]

DEFAULT_NOWPAYMENTS: Dict[str, Any] = {
    "sandbox": True,
    "api_key": "",
    "ipn_secret": "",
    "sandbox_api_key": "",
    "sandbox_ipn_secret": "",
}

DEFAULT_SETTINGS: Dict[str, Any] = {
    "id": "singleton",
    "express_surcharge_usd": 50.0,
    "max_upload_mb": 8,
    "whatsapp_admin": "+233000000000",
    "ai_model": "claude-sonnet-4-5-20250929",
    "usdt_discount_pct": 0.0,
    "hubtel": {
        "sandbox": True,
        "api_id": "",
        "api_key": "",
        "merchant_account_id": "",
        "callback_url": "",
        "return_url": "",
        "outbound_proxy_url": "",
    },
    "nowpayments": DEFAULT_NOWPAYMENTS,
    "visa_types": DEFAULT_VISA_TYPES,
    "payment_methods": DEFAULT_PAYMENT_METHODS,
    "updated_at": _now(),
}


def _tpl(name: str, lang: str, subject: str, html: str) -> Dict[str, Any]:
    return {
        "id": f"{name}_{lang}",
        "template_name": name,
        "lang": lang,
        "subject": subject,
        "html": html,
        "updated_at": _now(),
    }


BASE_CSS = "font-family:Inter,Arial,sans-serif;color:#0A0A0A;line-height:1.6;"
BOX = "border:1px solid #e5e7eb;border-radius:12px;padding:24px;max-width:560px;margin:24px auto;background:#fff;"
BADGE = "display:inline-block;padding:4px 10px;border-radius:999px;background:#006B3F;color:#fff;font-weight:600;letter-spacing:1px;font-size:12px;"

EMAIL_TEMPLATES_VERSION: int = 2  # bump to force re-seed of email_templates on next startup


def _wrap(title: str, body_html: str) -> str:
    return f"""<div style="{BASE_CSS}background:#F8FAFC;padding:24px 0;">
  <div style="{BOX}">
    <div style="text-align:center;margin-bottom:16px;">
      <div style="width:48px;height:48px;border-radius:50%;background:conic-gradient(#CE1126 0 33%,#FCD116 33% 66%,#006B3F 66% 100%);margin:0 auto 8px;display:flex;align-items:center;justify-content:center;color:#0A0A0A;font-weight:800;font-family:Outfit,sans-serif;">e</div>
      <div style="font-family:Outfit,sans-serif;font-weight:700;letter-spacing:.05em;">e.GHANA VISA</div>
    </div>
    <h2 style="font-family:Outfit,sans-serif;font-size:22px;margin:0 0 8px;">{title}</h2>
    {body_html}
    <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
    <p style="font-size:12px;color:#64748b;margin:0;">eghanavisa.com — Ghana Visa On Arrival Portal</p>
  </div>
</div>"""


def _badge(label: str) -> str:
    """Return a Ghana-green badge HTML snippet without str.format (preserves {{placeholders}})."""
    return '<span style="' + BADGE + '">' + label + '</span>'


DEFAULT_EMAIL_TEMPLATES: List[Dict[str, Any]] = [
    _tpl(
        "submitted", "en",
        "Your Ghana Visa Application {{tracking}} was received",
        _wrap(
            "Application Received",
            """
<p>Dear {{name}},</p>
<p>We've received your Ghana Visa On Arrival application. Below is your tracking number — please keep it safe.</p>
<p style="text-align:center;font-family:Outfit,sans-serif;font-size:28px;font-weight:700;letter-spacing:.05em;color:#006B3F;margin:24px 0;">{{tracking}}</p>
<p><strong>Visa:</strong> {{visa_type}}<br>
<strong>Processing:</strong> {{processing}}<br>
<strong>Amount paid:</strong> USD {{amount}}</p>
<p>You can follow the progress at any time on our tracking page.</p>
""",
        ),
    ),
    _tpl(
        "submitted", "fr",
        "Votre demande de visa Ghana {{tracking}} a été reçue",
        _wrap(
            "Demande reçue",
            """
<p>Bonjour {{name}},</p>
<p>Nous avons bien reçu votre demande de visa Ghana à l'arrivée. Voici votre numéro de suivi — conservez-le précieusement.</p>
<p style="text-align:center;font-family:Outfit,sans-serif;font-size:28px;font-weight:700;letter-spacing:.05em;color:#006B3F;margin:24px 0;">{{tracking}}</p>
<p><strong>Visa :</strong> {{visa_type}}<br>
<strong>Traitement :</strong> {{processing}}<br>
<strong>Montant payé :</strong> USD {{amount}}</p>
<p>Vous pouvez suivre l'avancement à tout moment sur notre page de suivi.</p>
""",
        ),
    ),
    _tpl(
        "in_progress", "en",
        "Update: Your Ghana Visa {{tracking}} is being processed",
        _wrap(
            "In Progress",
            """
<p>Dear {{name}},</p>
<p>Good news — your application <strong>{{tracking}}</strong> has moved to """ + _badge("IN PROGRESS") + """.</p>
<p>Our team is now reviewing your file. You will receive another email as soon as it is approved.</p>
""",
        ),
    ),
    _tpl(
        "in_progress", "fr",
        "Mise à jour : votre visa Ghana {{tracking}} est en cours de traitement",
        _wrap(
            "En cours",
            """
<p>Bonjour {{name}},</p>
<p>Bonne nouvelle — votre demande <strong>{{tracking}}</strong> est passée à l'étape """ + _badge("EN COURS") + """.</p>
<p>Notre équipe examine votre dossier. Vous recevrez un autre e-mail dès qu'il sera approuvé.</p>
""",
        ),
    ),
    _tpl(
        "done", "en",
        "Approved: Your Ghana Visa {{tracking}} is ready",
        _wrap(
            "Visa Approved",
            """
<p>Dear {{name}},</p>
<p>Congratulations — your Ghana Visa On Arrival <strong>{{tracking}}</strong> has been """ + _badge("APPROVED") + """.</p>
<p>Your electronic visa will be delivered to this email address shortly. Please travel with the printed copy and your passport.</p>
<p>Enjoy your stay in Ghana. 🇬🇭</p>
""",
        ),
    ),
    _tpl(
        "done", "fr",
        "Approuvé : votre visa Ghana {{tracking}} est prêt",
        _wrap(
            "Visa approuvé",
            """
<p>Bonjour {{name}},</p>
<p>Félicitations — votre visa Ghana à l'arrivée <strong>{{tracking}}</strong> a été """ + _badge("APPROUVÉ") + """.</p>
<p>Votre visa électronique sera envoyé à cette adresse e-mail sous peu. Voyagez avec la version imprimée et votre passeport.</p>
<p>Excellent séjour au Ghana. 🇬🇭</p>
""",
        ),
    ),
]
