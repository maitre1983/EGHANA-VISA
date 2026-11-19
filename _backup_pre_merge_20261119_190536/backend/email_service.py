"""Email delivery via Resend with automatic simulation/log fallback.

If RESEND_API_KEY is not configured, emails are stored in a MongoDB collection
`email_log` marked as simulated=True so admins can preview them in the dashboard.
"""
import os
import asyncio
import logging
import uuid
from datetime import datetime, timezone

import resend

logger = logging.getLogger(__name__)


class EmailService:
    # Template placeholder delimiters — safe Jinja-style, NOT a secret.
    _TPL_OPEN = "{" + "{"
    _TPL_CLOSE = "}" + "}"

    def __init__(self, db):
        self.db = db

    def _configured(self) -> bool:
        return bool(os.environ.get("RESEND_API_KEY", "").strip())

    async def render_template(self, template_name: str, lang: str, context: dict) -> tuple[str, str]:
        """Return (subject, html) for a template + language, applying variable substitution."""
        doc = await self.db.email_templates.find_one(
            {"template_name": template_name, "lang": lang}, {"_id": 0}
        )
        if not doc:
            # fallback to EN
            doc = await self.db.email_templates.find_one(
                {"template_name": template_name, "lang": "en"}, {"_id": 0}
            )
        if not doc:
            raise RuntimeError(f"Email template not found: {template_name}")
        subject = doc["subject"]
        html = doc["html"]
        for k, v in context.items():
            token = f"{self._TPL_OPEN}{k}{self._TPL_CLOSE}"
            subject = subject.replace(token, str(v))
            html = html.replace(token, str(v))
        return subject, html

    async def send(
        self,
        recipient: str,
        template_name: str,
        context: dict,
        lang: str = "en",
    ) -> dict:
        subject, html = await self.render_template(template_name, lang, context)
        entry = {
            "id": str(uuid.uuid4()),
            "recipient": recipient,
            "template_name": template_name,
            "lang": lang,
            "subject": subject,
            "html": html,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "simulated": True,
            "resend_id": None,
            "error": None,
        }

        if self._configured():
            try:
                resend.api_key = os.environ["RESEND_API_KEY"]
                sender = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
                params = {
                    "from": sender,
                    "to": [recipient],
                    "subject": subject,
                    "html": html,
                }
                email = await asyncio.to_thread(resend.Emails.send, params)
                entry["simulated"] = False
                entry["resend_id"] = email.get("id") if isinstance(email, dict) else None
            except Exception as e:
                logger.error(f"Resend send failed: {e}")
                entry["error"] = str(e)

        await self.db.email_log.insert_one(dict(entry))
        entry.pop("_id", None)
        return entry
