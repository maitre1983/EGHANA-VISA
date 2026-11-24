"""Admin activity audit log — pure ASGI middleware recording every admin write."""
import json
import re
import uuid
import logging
from datetime import datetime, timezone

from auth_utils import decode_token

logger = logging.getLogger(__name__)

SENSITIVE = re.compile(r"(pass|secret|key|token|api_id|proxy)", re.I)
AUDITED_GET = re.compile(r"^/api/admin/(transactions\.(csv|xlsx)|applications/[^/]+/documents/)")


def _redact(obj):
    if isinstance(obj, dict):
        return {k: ("***" if SENSITIVE.search(k) and v else _redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


def _should_audit(method: str, path: str) -> bool:
    if not path.startswith("/api/admin"):
        return False
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        return True
    return method == "GET" and bool(AUDITED_GET.match(path))


class AuditMiddleware:
    def __init__(self, app, db):
        self.app = app
        self.db = db

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not _should_audit(scope.get("method", ""), scope.get("path", "")):
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        status = {"code": 0}

        async def recv():
            msg = await receive()
            if msg["type"] == "http.request":
                chunks.append(msg.get("body", b""))
            return msg

        async def snd(msg):
            if msg["type"] == "http.response.start":
                status["code"] = msg["status"]
            await send(msg)

        try:
            await self.app(scope, recv, snd)
        finally:
            try:
                await self._record(scope, b"".join(chunks), status["code"])
            except Exception as e:
                logger.warning(f"audit log write failed: {e}")

    async def _record(self, scope, body: bytes, code: int):
        headers = {k.decode().lower(): v.decode(errors="replace") for k, v in scope.get("headers", [])}
        path = scope["path"]
        admin_email = ""
        auth = headers.get("authorization", "")
        if auth.startswith("Bearer "):
            try:
                admin_email = decode_token(auth.split(" ", 1)[1]).get("email", "")
            except Exception:
                admin_email = ""
        details = None
        if body and "multipart" not in headers.get("content-type", ""):
            try:
                details = _redact(json.loads(body.decode("utf-8")))
            except Exception:
                details = None
        if path == "/api/admin/login" and isinstance(details, dict):
            admin_email = admin_email or details.get("email", "")
        ip = headers.get("cf-connecting-ip") or (headers.get("x-forwarded-for", "").split(",")[0].strip())
        await self.db.admin_audit_log.insert_one({
            "id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "admin_email": admin_email,
            "method": scope["method"],
            "path": path,
            "query": scope.get("query_string", b"").decode()[:300],
            "status_code": code,
            "success": 200 <= code < 400,
            "details": details,
            "ip": ip,
        })
