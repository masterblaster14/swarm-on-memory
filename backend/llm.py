"""
Real LLM calls through the local Anthropic-compatible proxy.

Every call returns the text plus REAL token usage, which feeds the
ablation cost counter. No mocking.
"""
from __future__ import annotations
import asyncio
import json
import random
from dataclasses import dataclass, field

import httpx

from backend.config import (LLM_API_KEY, LLM_BASE_URL, LLM_MODEL,
                            PRICE_IN_PER_MTOK, PRICE_OUT_PER_MTOK)


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def cost_usd(self) -> float:
        return (self.prompt_tokens / 1_000_000 * PRICE_IN_PER_MTOK
                + self.completion_tokens / 1_000_000 * PRICE_OUT_PER_MTOK)

    def add(self, other: "Usage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens


@dataclass
class LLMResult:
    text: str
    usage: Usage


async def complete(system: str, user: str, max_tokens: int = 900,
                   temperature: float = 0.3) -> LLMResult:
    """Single-turn completion via the proxy's /v1/messages endpoint."""
    url = f"{LLM_BASE_URL}/v1/messages"
    payload = {
        "model": LLM_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "content-type": "application/json",
        "x-api-key": LLM_API_KEY,
        "anthropic-version": "2023-06-01",
    }
    data = await _post_with_retry(url, payload, headers)

    text = _extract_text(data)
    u = data.get("usage", {}) or {}
    usage = Usage(
        prompt_tokens=int(u.get("prompt_tokens", u.get("input_tokens", 0)) or 0),
        completion_tokens=int(u.get("completion_tokens", u.get("output_tokens", 0)) or 0),
    )
    return LLMResult(text=text, usage=usage)


async def _post_with_retry(url: str, payload: dict, headers: dict,
                           attempts: int = 5) -> dict:
    """Retry transient proxy errors (520/429/5xx) with jittered backoff.

    The local LLM proxy returns 520 under concurrent bursts; five agents fire
    at once, so a single attempt drops agents. Backoff makes the swarm robust.
    """
    last: Exception | None = None
    async with httpx.AsyncClient(timeout=120) as client:
        for i in range(attempts):
            try:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code in (429, 500, 502, 503, 504, 520, 522, 524):
                    raise httpx.HTTPStatusError(f"transient {r.status_code}",
                                                request=r.request, response=r)
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPStatusError, httpx.TransportError) as e:
                last = e
                if i == attempts - 1:
                    break
                await asyncio.sleep(min(8.0, 0.6 * (2 ** i)) + random.random() * 0.4)
    raise last  # type: ignore[misc]


def _extract_text(data: dict) -> str:
    # Proxy returns an OpenAI-style chat.completion even at /v1/messages.
    if "choices" in data:
        return data["choices"][0]["message"]["content"] or ""
    # Native Anthropic shape fallback.
    if "content" in data and isinstance(data["content"], list):
        return "".join(b.get("text", "") for b in data["content"])
    return json.dumps(data)[:2000]


async def complete_json(system: str, user: str, max_tokens: int = 1100) -> tuple[dict | list, Usage]:
    """Completion that must return JSON. Tolerant parse with one repair pass."""
    res = await complete(system + "\n\nRespond with ONLY valid JSON, no prose, no markdown fences.",
                         user, max_tokens=max_tokens, temperature=0.2)
    parsed = _loose_json(res.text)
    return parsed, res.usage


def _loose_json(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    # find first { or [ and last } or ]
    for open_c, close_c in (("{", "}"), ("[", "]")):
        i, j = text.find(open_c), text.rfind(close_c)
        if i != -1 and j != -1 and j > i:
            try:
                return json.loads(text[i:j + 1])
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text}
