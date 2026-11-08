"""Knowledge vault storage backends.

Production uses the existing Supabase project's Storage REST API. If storage
credentials are not configured (local development and tests), a filesystem
backend under ``backend/data/knowledge_vault`` is used. Vercel's filesystem is
never treated as durable; the factory therefore refuses to select the local
backend when running serverless.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, unquote

import httpx

from app.core.config import BASE_DIR, settings
from app.core.execution_provider import is_serverless_runtime
from app.core.logging import get_logger

logger = get_logger("iris.knowledge.storage")


class VaultStorageError(RuntimeError):
    pass


class VaultStorage(Protocol):
    backend: str

    def ensure_bucket(self) -> None: ...
    def put(self, path: str, content: str) -> None: ...
    def get(self, path: str) -> str | None: ...
    def delete(self, path: str) -> bool: ...
    def exists(self, path: str) -> bool: ...
    def list(self, prefix: str = "", limit: int = 1000) -> list[str]: ...


def _safe_relative(path: str) -> str:
    raw = path or ""
    for _ in range(5):
        unquoted = unquote(raw)
        if unquoted == raw:
            break
        raw = unquoted
    clean = raw.replace("\\", "/").lstrip("/")
    parts = [part for part in clean.split("/") if part not in {"", ".", ".."}]
    if not parts:
        raise VaultStorageError("A vault path is required.")
    return "/".join(parts)


@dataclass
class LocalVaultStorage:
    root: Path
    backend: str = "local"

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, path: str) -> Path:
        target = (self.root / _safe_relative(path)).resolve()
        if self.root.resolve() not in target.parents and target != self.root.resolve():
            raise VaultStorageError("Vault path escapes the configured root.")
        return target

    def ensure_bucket(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, path: str, content: str) -> None:
        target = self._path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(target)

    def get(self, path: str) -> str | None:
        target = self._path(path)
        if not target.is_file():
            return None
        return target.read_text(encoding="utf-8")

    def delete(self, path: str) -> bool:
        target = self._path(path)
        if target.is_file():
            target.unlink()
            return True
        return False

    def exists(self, path: str) -> bool:
        return self._path(path).is_file()

    def list(self, prefix: str = "", limit: int = 1000) -> list[str]:
        base = self.root
        if prefix:
            try:
                candidate = self._path(prefix.rstrip("/") + "/index")
                base = candidate.parent
            except VaultStorageError:
                base = self.root
        if not base.exists():
            return []
        found: list[str] = []
        for item in sorted(base.rglob("*.md")):
            if item.name.endswith(".tmp"):
                continue
            found.append(item.relative_to(self.root).as_posix())
            if len(found) >= limit:
                break
        return found

    def clear(self) -> None:  # test helper
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)


class SupabaseVaultStorage:
    """Supabase Storage REST client using the existing project credentials."""

    backend = "supabase"

    def __init__(self, url: str, service_key: str, bucket: str) -> None:
        self.base = url.rstrip("/") + "/storage/v1"
        self.bucket = bucket
        self.headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        }
        self._bucket_ready = False

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        req_headers = {**self.headers, **kwargs.pop("headers", {})}
        with httpx.Client(timeout=30.0) as client:
            response = client.request(method, f"{self.base}{path}", headers=req_headers, **kwargs)
        if response.status_code >= 500:
            raise VaultStorageError(f"Supabase Storage returned {response.status_code}.")
        return response

    def ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        response = self._request("GET", f"/bucket/{quote(self.bucket)}")
        is_missing = response.status_code == 404 or (
            response.status_code == 400
            and "NoSuchBucket" in response.text
        )
        if is_missing:
            created = self._request(
                "POST",
                "/bucket",
                json={"id": self.bucket, "name": self.bucket, "public": False},
            )
            if created.status_code not in {200, 201, 409}:
                raise VaultStorageError("Could not create the knowledge vault bucket.")
        elif response.status_code not in {200, 401, 403}:
            raise VaultStorageError("Could not inspect the knowledge vault bucket.")
        self._bucket_ready = True

    def put(self, path: str, content: str) -> None:
        self.ensure_bucket()
        clean_path = quote(_safe_relative(path), safe="/")
        response = self._request(
            "POST",
            f"/object/{quote(self.bucket)}/{clean_path}",
            content=content.encode("utf-8"),
            headers={"Content-Type": "text/markdown; charset=utf-8", "x-upsert": "true"},
        )
        if response.status_code not in {200, 201}:
            raise VaultStorageError("Knowledge vault upload failed.")

    def get(self, path: str) -> str | None:
        self.ensure_bucket()
        clean_path = quote(_safe_relative(path), safe="/")
        response = self._request(
            "GET", f"/object/{quote(self.bucket)}/{clean_path}"
        )
        if response.status_code == 404:
            return None
        if response.status_code == 400:
            try:
                err = response.json()
                if (
                    err.get("statusCode") in {"404", 404}
                    or err.get("code") in {"NoSuchKey", "NoSuchBucket"}
                    or err.get("error") in {"not_found", "Bucket not found"}
                ):
                    return None
            except Exception:
                pass
        if response.status_code != 200:
            raise VaultStorageError("Knowledge vault read failed.")
        return response.text

    def delete(self, path: str) -> bool:
        self.ensure_bucket()
        clean_path = quote(_safe_relative(path), safe="/")
        response = self._request(
            "DELETE", f"/object/{quote(self.bucket)}/{clean_path}"
        )
        return response.status_code in {200, 204, 404}

    def exists(self, path: str) -> bool:
        return self.get(path) is not None

    def list(self, prefix: str = "", limit: int = 1000) -> list[str]:
        self.ensure_bucket()
        clean_prefix = prefix.replace("\\", "/").strip("/")
        response = self._request(
            "POST",
            f"/object/list/{quote(self.bucket)}",
            json={
                "prefix": clean_prefix,
                "limit": min(limit, 1000),
                "offset": 0,
                "sortBy": {"column": "name", "order": "asc"},
            },
        )
        if response.status_code != 200:
            raise VaultStorageError("Knowledge vault listing failed.")
        found: list[str] = []
        for item in response.json() or []:
            name = item.get("name")
            if not name:
                continue
            path = f"{clean_prefix}/{name}".strip("/") if clean_prefix else name
            if item.get("id") is None:
                sub_items = self.list(prefix=path, limit=limit - len(found))
                found.extend(sub_items)
            elif name.endswith(".md"):
                found.append(path)
            if len(found) >= limit:
                break
        return found


def get_vault_storage() -> VaultStorage:
    storage_key = settings.supabase_service_role_key or settings.supabase_anon_key
    if settings.supabase_url and storage_key:
        return SupabaseVaultStorage(
            settings.supabase_url,
            storage_key,
            settings.knowledge_vault_bucket,
        )
    if is_serverless_runtime():
        raise VaultStorageError(
            "Supabase Storage credentials are required for the knowledge vault in serverless deployments."
        )
    root = (
        Path(settings.knowledge_vault_local_dir)
        if settings.knowledge_vault_local_dir
        else BASE_DIR / "data" / "knowledge_vault"
    )
    logger.info("knowledge_vault_using_local_backend root=%s", root)
    return LocalVaultStorage(root=root)
