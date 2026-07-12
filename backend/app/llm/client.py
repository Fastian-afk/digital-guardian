"""
client.py — Groq API Client (Phase 2 LLM Engine)
──────────────────────────────────────────────────
Uses Groq's ultra-fast inference API (llama3-70b-8192) as the cognitive
engine for semantic analysis. Groq is:
  - Free tier (generous limits)
  - ~500 tokens/sec (fastest available)
  - Zero local disk space
  - Drop-in compatible with our Ollama interface

Fallback chain:
  Groq API → Rule-based NLP (if API key missing or request fails)

JSON extraction: 3-strategy fallback if LLM deviates from schema.
"""
import re
import json
import asyncio
from typing import Optional

import httpx

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


# ─────────────────────────────────────────────────────────────────────────────
# JSON Extraction — 3-strategy fallback
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json_from_response(raw: str) -> Optional[dict]:
    """
    Extracts a valid JSON object from LLM response using 3 strategies:
      1. Direct JSON parse (ideal — LLM followed schema)
      2. Extract from markdown code fence (```json ... ```)
      3. Regex find first { ... } block
    """
    raw = raw.strip()

    # Strategy 1: Direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Code fence
    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: First { ... } block
    brace_match = re.search(r"\{[\s\S]+\}", raw)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning(f"[LLMClient] All JSON strategies failed. First 200 chars: {raw[:200]}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Groq Chat Completion
# ─────────────────────────────────────────────────────────────────────────────

async def ollama_chat(
    system_prompt: str,
    user_prompt: str,
    max_retries: int = 1,
) -> Optional[dict]:
    """
    Sends a chat request to Groq API.
    Function name kept as `ollama_chat` for zero-refactor compatibility
    with semantic_analyzer.py.

    Returns parsed JSON dict or None on any failure.
    """
    api_key = settings.GROQ_API_KEY
    if not api_key:
        logger.warning("[LLMClient] GROQ_API_KEY not set. Falling back to rule-based engine.")
        return None

    payload = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"},  # Groq JSON mode
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT) as client:
                response = await client.post(GROQ_API_URL, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

            raw_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not raw_content:
                logger.warning("[LLMClient] Empty content in Groq response.")
                return None

            parsed = _extract_json_from_response(raw_content)
            if parsed:
                usage = data.get("usage", {})
                logger.info(
                    f"[LLMClient] Groq response parsed ✅ | "
                    f"tokens: {usage.get('total_tokens', '?')} | "
                    f"attempt: {attempt + 1}"
                )
            return parsed

        except httpx.ConnectError:
            logger.warning("[LLMClient] Cannot connect to Groq API. Check internet connection.")
            return None

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("[LLMClient] Invalid GROQ_API_KEY. Check your .env file.")
                return None
            elif e.response.status_code == 429:
                logger.warning(f"[LLMClient] Groq rate limit hit. Attempt {attempt + 1}.")
                if attempt < max_retries:
                    await asyncio.sleep(2)
                    continue
            else:
                logger.error(f"[LLMClient] Groq HTTP {e.response.status_code}: {e.response.text[:200]}")
            return None

        except httpx.TimeoutException:
            logger.warning(f"[LLMClient] Groq request timed out (attempt {attempt + 1}).")
            if attempt < max_retries:
                await asyncio.sleep(1)
                continue
            return None

        except Exception as exc:
            logger.error(f"[LLMClient] Unexpected error: {exc}", exc_info=True)
            return None

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────────────────────────────────────

async def check_ollama_health() -> bool:
    """
    Checks if Groq API is reachable and the API key is valid.
    Used by the /health endpoint.
    """
    api_key = settings.GROQ_API_KEY
    if not api_key:
        return False

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            return response.status_code == 200
    except Exception:
        return False
