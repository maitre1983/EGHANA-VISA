"""Storage abstraction — Emergent Object Storage backend with future R2/S3 migration path."""
import os
import uuid
import logging
import requests
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
APP_NAME = os.environ.get("APP_NAME", "eghanavisa")


class StorageService(ABC):
    """Abstract file storage. Any backend must implement these 3 methods."""

    @abstractmethod
    def put(self, path: str, data: bytes, content_type: str) -> dict: ...

    @abstractmethod
    def get(self, path: str) -> tuple[bytes, str]: ...

    @abstractmethod
    def build_path(self, tracking_no: str, doc_type: str, ext: str) -> str: ...


class EmergentStorageBackend(StorageService):
    def __init__(self):
        self._key = None

    def _init_key(self):
        if self._key:
            return self._key
        emergent_key = os.environ.get("EMERGENT_LLM_KEY")
        if not emergent_key:
            raise RuntimeError("EMERGENT_LLM_KEY not set")
        resp = requests.post(
            f"{STORAGE_URL}/init",
            json={"emergent_key": emergent_key},
            timeout=30,
        )
        resp.raise_for_status()
        self._key = resp.json()["storage_key"]
        logger.info("Emergent storage initialized")
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


# Singleton
storage: StorageService = EmergentStorageBackend()


ALLOWED_EXTS = {"jpg", "jpeg", "png", "pdf"}
MIME_MAP = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "pdf": "application/pdf",
}


def validate_file(filename: str, size_bytes: int, max_mb: int) -> str:
    """Return the lowercase extension if OK, else raise ValueError."""
    if "." not in filename:
        raise ValueError("File must have an extension")
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTS:
        raise ValueError(f"Format not allowed. Allowed: JPEG, PNG, PDF")
    if size_bytes > max_mb * 1024 * 1024:
        raise ValueError(f"File exceeds max size of {max_mb} MB")
    return ext
