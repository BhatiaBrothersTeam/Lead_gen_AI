"""
One JSON-returning AI call, using the same provider settings as the lead
pipeline (AI_PROVIDER = "claude" (default) or "groq", with ANTHROPIC_API_KEY /
GROQ_API_KEY / GROQ_MODEL). Used by the Lead Matchmaker module.

Callers treat every failure as "no AI answer" and fall back to rule-based
logic, so this raises AIUnavailable instead of returning partial data.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

# Claude model for Lead Matchmaker research and drafts. Override with MATCHMAKER_CLAUDE_MODEL.
DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"


class AIUnavailable(RuntimeError):
    """No provider configured, the call failed, or the answer was not usable JSON."""


def provider() -> str:
    return (os.getenv("AI_PROVIDER") or "claude").strip().lower()


def ai_configured() -> bool:
    if provider() == "groq":
        return bool(os.getenv("GROQ_API_KEY"))
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _parse_json(text: str) -> Any:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except ValueError:
        # Tolerate a sentence before/after the object.
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except ValueError:
                pass
    raise AIUnavailable("The AI answer was not valid JSON")


async def _claude(system: str, prompt: str, max_tokens: int) -> str:
    client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=90.0, max_retries=2)
    model = os.getenv("MATCHMAKER_CLAUDE_MODEL") or DEFAULT_CLAUDE_MODEL
    # Low effort: this is extraction/rewriting, not open-ended reasoning.
    # Server-side fallback: if a safety classifier declines, the API retries on
    # a fallback model in the same call instead of returning nothing.
    response = await client.beta.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        extra_body={"fallbacks": "default"},
    )
    if response.stop_reason == "refusal":
        raise AIUnavailable("The AI provider declined the request")
    # Thinking blocks come first on current models: take the text blocks only.
    return "".join(b.text for b in response.content if getattr(b, "type", "") == "text")


async def _groq(system: str, prompt: str, max_tokens: int) -> str:
    payload = {
        "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        res = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
            json=payload,
        )
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]


async def complete_json(system: str, prompt: str, max_tokens: int = 4000) -> Any:
    """Ask the configured provider for a JSON answer. Raises AIUnavailable on any failure."""
    if not ai_configured():
        raise AIUnavailable("No AI provider key is configured")
    try:
        text = await (_groq if provider() == "groq" else _claude)(system, prompt, max_tokens)
    except AIUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 -- any provider error means "no AI answer"
        # The exception type only: provider errors can echo request details.
        logger.warning("AI call failed (%s): %s", provider(), type(exc).__name__)
        raise AIUnavailable(f"AI provider error ({type(exc).__name__})") from exc
    return _parse_json(text)
