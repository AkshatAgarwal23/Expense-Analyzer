"""Sarvam AI speech-to-text (Indian languages / Hinglish).

POST https://api.sarvam.ai/speech-to-text
Docs: https://docs.sarvam.ai/api-reference/speech-to-text/transcribe

Default mode is `translit` (romanized Hinglish) so amount/friend regex still works.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from app.config import settings
from app.services.errors import DomainError, ValidationError


class TranscriptionError(DomainError):
    pass


def _guess_content_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".mp4": "audio/mp4",
        ".webm": "audio/webm",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".aac": "audio/aac",
    }.get(suffix, "application/octet-stream")


def transcribe(audio_bytes: bytes, filename: str) -> str:
    if not audio_bytes:
        raise ValidationError("Empty audio file")
    if not settings.sarvam_api_key.strip():
        raise TranscriptionError(
            "SARVAM_API_KEY is not set. Add it to your .env file."
        )

    safe_name = Path(filename).name or "audio.webm"
    headers = {"api-subscription-key": settings.sarvam_api_key.strip()}
    data = {
        "model": settings.sarvam_model,
        "mode": settings.sarvam_mode,
        "language_code": settings.sarvam_language_code,
    }
    files = {
        "file": (safe_name, audio_bytes, _guess_content_type(safe_name)),
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                settings.sarvam_api_url,
                headers=headers,
                data=data,
                files=files,
            )
    except httpx.HTTPError as exc:
        raise TranscriptionError(f"Sarvam request failed: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text
        try:
            payload = response.json()
            err = payload.get("error") or payload
            if isinstance(err, dict):
                detail = err.get("message") or str(err)
            else:
                detail = str(payload)
        except Exception:  # noqa: BLE001
            pass
        raise TranscriptionError(
            f"Sarvam STT failed ({response.status_code}): {detail}"
        )

    try:
        body = response.json()
    except Exception as exc:  # noqa: BLE001
        raise TranscriptionError("Sarvam returned non-JSON response") from exc

    transcript = (body.get("transcript") or "").strip()
    if not transcript:
        raise TranscriptionError("Sarvam returned an empty transcript")
    return transcript
