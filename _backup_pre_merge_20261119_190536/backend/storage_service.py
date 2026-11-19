"""Storage abstraction — Cloudflare R2 (primary) + Emergent Object Storage (legacy fallback).

Architecture:
- MongoDB stores structured application data and *pointers* to the actual files.
- Cloudflare R2 stores every new binary blob, under an env-scoped folder tree:
    {env}/applicants/{tracking_no}/photos/{uuid}.{ext}
    {env}/applicants/{tracking_no}/passports/{uuid}.{ext}
    {env}/applicants/{tracking_no}/supporting-documents/{uuid}.{ext}
    {env}/payments/{tracking_no}/{uuid}.{ext}
    {env}/invoices/{tracking_no}/{uuid}.{ext}
    {env}/exports/{yyyy-mm-dd}/{uuid}.{ext}
- Bucket stays private. Downloads are served via short-lived S3 pre-signed URLs
  (default 15 min TTL) either through the R2 native endpoint OR through a
  configured custom CDN domain (e.g. https://cdn.eghanavisa.com).
- If R2 is not configured yet, the service transparently falls back to the
  Emergent Object Storage backend so legacy files keep working.

All configuration is read from the admin `settings.r2` document — nothing is
hardcoded. Callers do not need to know which backend they are hitting."""
from __future__ import annotations

import os
import uuid
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ─────────────────── Legacy Emergent backend ───────────────────
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
APP_NAME = os.environ.get("APP_NAME", "eghanavisa")


class StorageService(ABC):
    name: str = "abstract"

    @abstractmethod
    def put(self, path: str, data: bytes, content_type: str) -> dict: ...

    @abstractmethod
    def get(self, path: str) -> tuple[bytes, str]: ...

    def signed_url(self, path: str, expires_in: int = 900, content_type: Optional[str] = None) -> Optional[str]:
        """Return a short-lived download URL, or None if the backend cannot presign."""
        return None

    def delete(self, path: str) -> bool:
        """Delete a single object. Return True if backend supports deletion."""
        return False

    def delete_prefix(self, prefix: str) -> int:
        """Delete every object under `prefix`. Return number of objects deleted."""
        return 0

    @abstractmethod
    def build_path(self, tracking_no: str, doc_type: str, ext: str) -> str: ...

    def test_connection(self) -> dict:
        return {"ok": False, "backend": self.name, "detail": "test_connection not implemented"}


# ─────────────────── Emergent (legacy) ───────────────────

class EmergentStorageBackend(StorageService):
    name = "emergent"

    def __init__(self):
        self._key = None

    def _init_key(self):
        if self._key:
            return self._key
        emergent_key = os.environ.get("EMERGENT_LLM_KEY")
        if not emergent_key:
            raise RuntimeError("EMERGENT_LLM_KEY not set")
        resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": emergent_key}, timeout=30)
        resp.raise_for_status()
        self._key = resp.json()["storage_key"]
        return self._key

    def put(self, path: str, data: bytes, content_type: str) -> dict:
        key = self._init_key()
        resp = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()

    def get(self, path: str) -> tuple[bytes, str]:
        key = self._init_key()
        resp = requests.get(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

    def build_path(self, tracking_no: str, doc_type: str, ext: str) -> str:
        return f"{APP_NAME}/applications/{tracking_no}/{doc_type}-{uuid.uuid4()}.{ext}"


# ─────────────────── Cloudflare R2 (S3-compatible) ───────────────────

# Map document type → subfolder inside applicants/{tracking_no}/
DOC_FOLDER_MAP = {
    "face_photo": "photos",
    "passport_copy": "passports",
    "passport_cover": "passports",
    "flight_ticket": "supporting-documents",
    # Any custom/other doc type ends up in supporting-documents
}


def detect_environment() -> str:
    """Detect the deployment environment. Order:
    1) STORAGE_ENV explicit override
    2) EMERGENT_ENV (set by platform)
    3) Infer from platform env vars (preview_endpoint / hostname)
    4) Fallback → 'development'"""
    override = os.environ.get("STORAGE_ENV")
    if override:
        return override.lower().strip()
    plat = os.environ.get("EMERGENT_ENV")
    if plat:
        return plat.lower().strip()
    for var in ("APP_URL", "PREVIEW_ENDPOINT", "preview_endpoint", "PUBLIC_URL", "REACT_APP_BACKEND_URL"):
        url = os.environ.get(var, "")
        if not url:
            continue
        low = url.lower()
        if "eghanavisa.com" in low:
            return "production"
        if "preview.emergentagent" in low or "preview." in low:
            return "preview"
    return "development"


class R2StorageBackend(StorageService):
    """Cloudflare R2 backend using the S3-compatible protocol.

    Bucket stays private; all reads are served through boto3-generated
    pre-signed URLs. If a custom CDN domain is configured we generate the
    signature against that hostname so downloads flow through the CDN."""

    name = "r2"

    def __init__(self, config: dict):
        self._config = dict(config or {})
        self._client = None
        self._presign_client = None  # separate client if CDN domain differs from R2 endpoint

    # ---- Config helpers ----
    @property
    def account_id(self) -> str:
        return str(self._config.get("account_id") or "").strip()

    @property
    def bucket(self) -> str:
        return str(self._config.get("bucket") or "").strip()

    @property
    def access_key_id(self) -> str:
        return str(self._config.get("access_key_id") or "").strip()

    @property
    def secret_access_key(self) -> str:
        return str(self._config.get("secret_access_key") or "").strip()

    @property
    def cdn_domain(self) -> str:
        raw = str(self._config.get("cdn_domain") or "").strip()
        if not raw:
            return ""
        # Strip protocol so we can rebuild it cleanly
        return raw.replace("https://", "").replace("http://", "").rstrip("/")

    @property
    def env_prefix(self) -> str:
        p = str(self._config.get("env_prefix") or "").strip()
        return p or detect_environment()

    @property
    def signed_url_ttl(self) -> int:
        try:
            v = int(self._config.get("signed_url_ttl") or 900)
        except (TypeError, ValueError):
            v = 900
        return max(60, min(v, 24 * 3600))  # clamp: 1 min .. 24 hrs

    def _endpoint(self) -> str:
        return f"https://{self.account_id}.r2.cloudflarestorage.com"

    def is_configured(self) -> bool:
        return all([self.account_id, self.bucket, self.access_key_id, self.secret_access_key])

    # ---- Boto clients (lazy) ----
    def _make_client(self, endpoint_url: str):
        import boto3
        from botocore.config import Config as BotoConfig
        return boto3.client(
            "s3",
            region_name="auto",
            endpoint_url=endpoint_url,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            config=BotoConfig(signature_version="s3v4"),
        )

    def _get_client(self):
        if self._client is None:
            self._client = self._make_client(self._endpoint())
        return self._client

    def _get_presign_client(self):
        # If a CDN domain is configured, presigned URLs must be signed against it
        # (S3v4 includes the host in the signature). Otherwise reuse main client.
        if self.cdn_domain:
            if self._presign_client is None:
                self._presign_client = self._make_client(f"https://{self.cdn_domain}")
            return self._presign_client
        return self._get_client()

    # ---- Interface ----
    def put(self, path: str, data: bytes, content_type: str) -> dict:
        client = self._get_client()
        try:
            client.put_object(
                Bucket=self.bucket,
                Key=path,
                Body=data,
                ContentType=content_type,
            )
        except Exception as e:
            logger.error(f"R2 put failed for {path}: {e}")
            raise
        return {"path": path, "size": len(data), "backend": "r2"}

    def get(self, path: str) -> tuple[bytes, str]:
        client = self._get_client()
        obj = client.get_object(Bucket=self.bucket, Key=path)
        return obj["Body"].read(), obj.get("ContentType", "application/octet-stream")

    def signed_url(self, path: str, expires_in: int = 0, content_type: Optional[str] = None) -> Optional[str]:
        client = self._get_presign_client()
        ttl = expires_in or self.signed_url_ttl
        try:
            return client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": path},
                ExpiresIn=ttl,
            )
        except Exception as e:
            logger.error(f"R2 signed URL failed for {path}: {e}")
            return None

    def delete(self, path: str) -> bool:
        client = self._get_client()
        try:
            client.delete_object(Bucket=self.bucket, Key=path)
            return True
        except Exception as e:
            logger.error(f"R2 delete failed for {path}: {e}")
            return False

    def delete_prefix(self, prefix: str) -> int:
        client = self._get_client()
        deleted = 0
        try:
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                objects = [{"Key": o["Key"]} for o in page.get("Contents", [])]
                if not objects:
                    continue
                # R2 supports batch delete up to 1000 keys
                for i in range(0, len(objects), 1000):
                    chunk = objects[i:i + 1000]
                    client.delete_objects(Bucket=self.bucket, Delete={"Objects": chunk, "Quiet": True})
                    deleted += len(chunk)
        except Exception as e:
            logger.error(f"R2 delete_prefix failed for {prefix}: {e}")
        return deleted

    def build_path(self, tracking_no: str, doc_type: str, ext: str) -> str:
        env = self.env_prefix
        subfolder = DOC_FOLDER_MAP.get(doc_type, "supporting-documents")
        return f"{env}/applicants/{tracking_no}/{subfolder}/{doc_type}-{uuid.uuid4()}.{ext}"

    def build_generic_path(self, category: str, tracking_no: Optional[str], ext: str) -> str:
        env = self.env_prefix
        if category == "exports":
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            return f"{env}/exports/{day}/{uuid.uuid4()}.{ext}"
        if tracking_no:
            return f"{env}/{category}/{tracking_no}/{uuid.uuid4()}.{ext}"
        return f"{env}/{category}/{uuid.uuid4()}.{ext}"

    def applicant_prefix(self, tracking_no: str) -> str:
        return f"{self.env_prefix}/applicants/{tracking_no}/"

    def test_connection(self) -> dict:
        """HEAD the bucket to confirm connectivity and credentials."""
        if not self.is_configured():
            return {"ok": False, "backend": "r2", "detail": "Missing account_id / bucket / access_key_id / secret_access_key"}
        try:
            client = self._get_client()
            client.head_bucket(Bucket=self.bucket)
            # Also do a tiny put+delete round-trip to prove write access
            probe_key = f"{self.env_prefix}/.egv-connection-probe.txt"
            client.put_object(Bucket=self.bucket, Key=probe_key, Body=b"ok", ContentType="text/plain")
            client.delete_object(Bucket=self.bucket, Key=probe_key)
            return {
                "ok": True,
                "backend": "r2",
                "bucket": self.bucket,
                "env_prefix": self.env_prefix,
                "cdn_domain": self.cdn_domain or None,
                "signed_url_ttl": self.signed_url_ttl,
            }
        except Exception as e:
            return {"ok": False, "backend": "r2", "detail": f"{type(e).__name__}: {str(e)[:400]}"}


# ─────────────────── Selector ───────────────────
_legacy_singleton = EmergentStorageBackend()


def get_backend(settings: Optional[dict]) -> StorageService:
    """Pick the active backend based on runtime settings. R2 wins if configured,
    otherwise falls back to Emergent so legacy files keep working."""
    r2_cfg = ((settings or {}).get("r2") or {}) if isinstance(settings, dict) else {}
    if r2_cfg and r2_cfg.get("enabled") is False:
        return _legacy_singleton
    r2 = R2StorageBackend(r2_cfg)
    if r2.is_configured():
        return r2
    return _legacy_singleton


def get_backend_for_path(path: str, settings: Optional[dict]) -> StorageService:
    """Choose the backend that owns a *previously-stored* file. R2 paths start
    with an env prefix like `production/`, `preview/`, `development/`. Legacy
    Emergent paths start with `{APP_NAME}/…`."""
    if not path:
        return _legacy_singleton
    if path.startswith((f"{APP_NAME}/", "eghanavisa/")):
        return _legacy_singleton
    r2_cfg = ((settings or {}).get("r2") or {}) if isinstance(settings, dict) else {}
    r2 = R2StorageBackend(r2_cfg)
    if r2.is_configured():
        return r2
    return _legacy_singleton


# ─────────────────── File validation (unchanged) ───────────────────
ALLOWED_EXTS = {"jpg", "jpeg", "png", "pdf"}
MIME_MAP = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "pdf": "application/pdf",
}


def validate_file(filename: str, size_bytes: int, max_mb: int) -> str:
    if "." not in filename:
        raise ValueError("File must have an extension")
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTS:
        raise ValueError("Format not allowed. Allowed: JPEG, PNG, PDF")
    if size_bytes > max_mb * 1024 * 1024:
        raise ValueError(f"File exceeds max size of {max_mb} MB")
    return ext


# Kept for backwards compatibility with existing imports (legacy default)
storage: StorageService = _legacy_singleton
