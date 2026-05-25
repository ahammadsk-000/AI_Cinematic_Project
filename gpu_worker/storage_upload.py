"""Upload final artifacts to shared object storage (Supabase Storage) so the
always-on backend / browser can serve them — the worker and the web app run on
different machines and don't share a filesystem.

Best-effort and config-gated: if SUPABASE_URL + SUPABASE_SERVICE_KEY aren't set,
upload() returns None and the caller falls back to the local /media path. Uses
httpx (already a dependency) — no extra SDK.

Setup (one time):
  * Supabase dashboard -> Storage -> create a PUBLIC bucket named `cineforge`.
  * Provide env: SUPABASE_URL (e.g. https://<ref>.supabase.co),
    SUPABASE_SERVICE_KEY (Settings -> API -> service_role key).
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Optional

import httpx

from ai_engine.utils.logging import get_logger

log = get_logger("storage")


def _config() -> Optional[tuple[str, str, str]]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    bucket = os.getenv("CINEFORGE_BUCKET", "cineforge")
    if url and key:
        return url, key, bucket
    return None


def is_configured() -> bool:
    return _config() is not None


def upload(local_path: Path, dest_path: str) -> Optional[str]:
    """Upload a file to Supabase Storage; return its public URL, or None if storage
    isn't configured / the upload fails (caller then keeps the local path)."""
    cfg = _config()
    if cfg is None:
        return None
    base, key, bucket = cfg
    content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
    upload_url = f"{base}/storage/v1/object/{bucket}/{dest_path}"
    try:
        data = Path(local_path).read_bytes()
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                upload_url,
                content=data,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": content_type,
                    "x-upsert": "true",  # overwrite on re-generate
                },
            )
            resp.raise_for_status()
        public_url = f"{base}/storage/v1/object/public/{bucket}/{dest_path}"
        log.info("uploaded %s -> %s", local_path.name, public_url)
        return public_url
    except Exception as exc:  # noqa: BLE001 - best effort
        log.warning("storage upload failed for %s: %s", local_path.name, exc)
        return None
