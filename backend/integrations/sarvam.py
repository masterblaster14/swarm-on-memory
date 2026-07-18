"""
Sarvam AI speech-to-text. Real multipart upload; the key stays server-side.

The browser records mic audio (webm/opus) and POSTs the blob to /api/stt,
which forwards it here. Sarvam returns a plain transcript we hand back.
"""
from __future__ import annotations

import asyncio

import httpx

from backend.config import (SARVAM_API_KEY, SARVAM_STT_LANGUAGE,
                            SARVAM_STT_MODEL, SARVAM_STT_URL)


def enabled() -> bool:
    return bool(SARVAM_API_KEY)


async def transcribe(audio: bytes, filename: str = "speech.webm",
                     content_type: str = "audio/webm") -> dict:
    """Transcribe an audio blob via Sarvam's REST STT endpoint."""
    if not SARVAM_API_KEY:
        return {"ok": False, "error": "SARVAM_API_KEY not configured"}
    if not audio:
        return {"ok": False, "error": "empty audio"}

    files = {"file": (filename, audio, content_type)}
    data = {"model": SARVAM_STT_MODEL, "language_code": SARVAM_STT_LANGUAGE}
    headers = {"api-subscription-key": SARVAM_API_KEY}

    last_err = ""
    async with httpx.AsyncClient(timeout=60) as client:
        for attempt in range(3):
            try:
                r = await client.post(SARVAM_STT_URL, headers=headers,
                                      files=files, data=data)
            except httpx.HTTPError as e:
                last_err = f"network: {e}"
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            if r.status_code == 200:
                body = r.json()
                return {"ok": True,
                        "transcript": (body.get("transcript") or "").strip(),
                        "language_code": body.get("language_code")}
            # 429/5xx are transient; retry. 4xx (bad audio/key) is not.
            last_err = f"sarvam {r.status_code}: {r.text[:300]}"
            if r.status_code in (429, 500, 502, 503, 504):
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            break
    return {"ok": False, "error": last_err or "sarvam request failed"}
