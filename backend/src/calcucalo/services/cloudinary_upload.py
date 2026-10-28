"""Cloudinary image upload service.

Reads credentials from environment variables:
    CLOUDINARY_CLOUD_NAME
    CLOUDINARY_API_KEY
    CLOUDINARY_API_SECRET

Optional:
    CLOUDINARY_FOLDER   – upload folder / prefix (default: "calcucalo")
    CLOUDINARY_PRESET   – unsigned upload preset; when set, uses unsigned upload
                          (api_key/api_secret are not needed in that mode).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any

import httpx


class CloudinaryConfigError(RuntimeError):
    """Raised when Cloudinary credentials are missing."""


class CloudinaryUploadError(RuntimeError):
    """Raised when the Cloudinary API returns an error."""


def _settings() -> dict[str, str]:
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
    api_key = os.getenv("CLOUDINARY_API_KEY", "").strip()
    api_secret = os.getenv("CLOUDINARY_API_SECRET", "").strip()
    if not cloud_name:
        raise CloudinaryConfigError(
            "CLOUDINARY_CLOUD_NAME is not set. "
            "Add it to backend/.env to enable image uploads."
        )
    if not api_key or not api_secret:
        raise CloudinaryConfigError(
            "CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET are required for signed uploads."
        )
    return {"cloud_name": cloud_name, "api_key": api_key, "api_secret": api_secret}


def _sign(params: dict[str, str], api_secret: str) -> str:
    """Generate Cloudinary signature for signed upload."""
    sorted_params = "&".join(
        f"{k}={v}" for k, v in sorted(params.items()) if k not in ("file", "api_key")
    )
    to_sign = sorted_params + api_secret
    return hashlib.sha256(to_sign.encode("utf-8")).hexdigest()


def upload_image(
    image_bytes: bytes,
    *,
    filename: str = "upload",
    resource_type: str = "image",
) -> str:
    """Upload raw image bytes to Cloudinary and return the secure URL.

    Args:
        image_bytes: Raw bytes of the image file.
        filename: Original filename hint (used as public_id base).
        resource_type: Cloudinary resource type, default "image".

    Returns:
        Cloudinary secure_url string.

    Raises:
        CloudinaryConfigError: Credentials missing.
        CloudinaryUploadError: Upload failed.
    """
    cfg = _settings()
    folder = os.getenv("CLOUDINARY_FOLDER", "calcucalo")
    timestamp = str(int(time.time()))

    # Build public_id from filename (strip extension, sanitize)
    stem = os.path.splitext(filename)[0]
    safe_stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)[:80]
    public_id = f"{folder}/{safe_stem}_{timestamp}" if folder else f"{safe_stem}_{timestamp}"

    params: dict[str, str] = {
        "timestamp": timestamp,
        "public_id": public_id,
    }
    signature = _sign(params, cfg["api_secret"])

    url = f"https://api.cloudinary.com/v1_1/{cfg['cloud_name']}/{resource_type}/upload"

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            url,
            data={
                **params,
                "api_key": cfg["api_key"],
                "signature": signature,
            },
            files={"file": (filename, image_bytes)},
        )

    if response.status_code != 200:
        try:
            detail = response.json().get("error", {}).get("message", response.text)
        except Exception:
            detail = response.text
        raise CloudinaryUploadError(f"Cloudinary upload failed: {detail}")

    result: dict[str, Any] = response.json()
    secure_url = result.get("secure_url", "")
    if not secure_url:
        raise CloudinaryUploadError("Cloudinary response did not contain a secure_url")
    return str(secure_url)


def cloudinary_is_configured() -> bool:
    """Return True when all required Cloudinary env vars are present."""
    return bool(
        os.getenv("CLOUDINARY_CLOUD_NAME")
        and os.getenv("CLOUDINARY_API_KEY")
        and os.getenv("CLOUDINARY_API_SECRET")
    )
