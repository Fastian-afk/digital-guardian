"""
Agent B: Semantic Analyzer — Phase 2
──────────────────────────────────────
Dual-engine architecture:
  PRIMARY:  Local LLM via Ollama (llama3 or any compatible model)
  FALLBACK: Rule-based regex NLP engine (Phase 1)

The fallback activates automatically if:
  - Ollama is not running
  - LLM times out
  - LLM returns malformed JSON after all extraction strategies fail

This means the system ALWAYS returns results — Ollama is optional but
makes the analysis significantly deeper when available.

Upgrade path from Phase 1:
  - Interface (inputs/outputs) is IDENTICAL — zero changes to router or synthesizer.
  - Only this file changes between Phase 1 and Phase 2.
"""
import re
from typing import List, Optional

from app.schemas.analysis import ExplainabilityMarker
from app.llm.client import ollama_chat
from app.llm.prompts import SYSTEM_PROMPT, build_analysis_prompt
from app.utils.logger import get_logger
from app.config import get_settings

logger = get_logger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 Rule-Based Engine (Fallback)
# ─────────────────────────────────────────────────────────────────────────────

_RULES: list[tuple] = [
    (
        re.compile(
            r"\b(shocking|explosive|bombshell|stunning|jaw-dropping|unbelievable|"
            r"you won't believe|mind-blowing|incredible|outrageous|scandalous|"
            r"breaking|urgent|alert|must-see|secret)\b",
            re.IGNORECASE,
        ),
        "Sensationalism", 0.78,
        "This phrase uses emotionally charged, clickbait-style language designed to provoke a strong reaction rather than inform objectively.",
    ),
    (
        re.compile(
            r"\b(allegedly|supposedly|rumored to|sources say|insiders claim|"
            r"some say|it is believed|experts suggest|many people think|"
            r"could be|might prove|may have)\b",
            re.IGNORECASE,
        ),
        "Unverified Claim", 0.72,
        "This phrase introduces a claim without citing a verifiable, named source, which is a common pattern in misinformation.",
    ),
    (
        re.compile(
            r"\b(they don't want you to know|the mainstream media hides|"
            r"what they're not telling you|the real truth|cover-up|"
            r"deep state|shadow government|wake up|sheeple|"
            r"do your own research|question everything)\b",
            re.IGNORECASE,
        ),
        "Conspiracy Language", 0.85,
        "This phrase is a known rhetorical device used in conspiracy content to undermine institutional trust without providing evidence.",
    ),
    (
        re.compile(
            r"\b(always|never|everyone knows|nobody believes|"
            r"all [a-z]+ are|the entire|completely|totally|absolutely|"
            r"100%|without exception|undeniably|proven fact)\b",
            re.IGNORECASE,
        ),
        "Absolute Language", 0.65,
        "Absolute language overstates certainty and is rarely appropriate in factual reporting, suggesting rhetorical manipulation.",
    ),
    (
        re.compile(
            r"\b(disaster|catastrophe|apocalypse|collapse|invasion|war|"
            r"crisis|emergency|threat|danger|attack|destroy|eliminate|"
            r"wipe out|end of|worst ever|unprecedented)\b",
            re.IGNORECASE,
        ),
        "Loaded Language", 0.60,
        "This word carries strong negative connotations that may be used to trigger fear or urgency beyond what the facts support.",
    ),
    (
        re.compile(
            r"\b(cure|miracle|guaranteed|100% effective|no side effects|"
            r"doctors hate|big pharma|natural remedy|detox|"
            r"ancient secret|suppress)\b",
            re.IGNORECASE,
        ),
        "Health Misinformation", 0.82,
        "This phrase matches patterns commonly found in pseudoscientific health claims. Always verify medical claims with certified health organizations.",
    ),
]


def _rule_based_analyze(content: str) -> List[ExplainabilityMarker]:
    """Phase 1 engine — used as fallback when LLM is unavailable."""
    markers: List[ExplainabilityMarker] = []
    seen: set[str] = set()

    for chunk in _chunk_text(content):
        for pattern, flag_type, confidence, explanation in _RULES:
            for match in pattern.finditer(chunk):
                word = match.group(0).lower()
                if word in seen:
                    continue
                seen.add(word)

                start = max(0, match.start() - 80)
                end = min(len(chunk), match.end() + 80)
                snippet = chunk[start:end].strip()
                if start > 0:
                    snippet = "..." + snippet
                if end < len(chunk):
                    snippet = snippet + "..."

                markers.append(ExplainabilityMarker(
                    text_segment=snippet,
                    flag_type=flag_type,
                    confidence=confidence,
                    explanation=explanation,
                ))
    return markers


# ─────────────────────────────────────────────────────────────────────────────
# LLM Response → ExplainabilityMarker Converter
# ─────────────────────────────────────────────────────────────────────────────

VALID_FLAG_TYPES = {
    "Sensationalism", "Unverified Claim", "Logical Fallacy", "Loaded Language",
    "Conspiracy Language", "Absolute Language", "Health Misinformation",
    "AI Hallucination Marker", "False Equivalence", "Missing Context",
}


def _parse_llm_markers(llm_response: dict, original_chunk: str) -> List[ExplainabilityMarker]:
    """
    Converts raw LLM JSON dict into validated ExplainabilityMarker objects.
    Applies strict validation — malformed markers are skipped, not crashed on.
    """
    markers = []
    raw_markers = llm_response.get("markers", [])

    if not isinstance(raw_markers, list):
        logger.warning("[SemanticAnalyzer] LLM returned non-list markers field.")
        return markers

    for item in raw_markers:
        try:
            text_segment = str(item.get("text_segment", "")).strip()
            flag_type = str(item.get("flag_type", "")).strip()
            confidence = float(item.get("confidence", 0.5))
            explanation = str(item.get("explanation", "")).strip()

            # Validate required fields
            if not text_segment or len(text_segment) < 5:
                continue
            if not explanation:
                continue

            # Normalize flag type
            if flag_type not in VALID_FLAG_TYPES:
                flag_type = "Unverified Claim"  # Safe default

            # Clamp confidence
            confidence = max(0.0, min(1.0, confidence))

            # Truncate segment to 200 chars max
            if len(text_segment) > 200:
                text_segment = text_segment[:197] + "..."

            markers.append(ExplainabilityMarker(
                text_segment=text_segment,
                flag_type=flag_type,
                confidence=confidence,
                explanation=explanation,
            ))

        except (TypeError, ValueError) as e:
            logger.warning(f"[SemanticAnalyzer] Skipping malformed marker: {e}")
            continue

    return markers


# ─────────────────────────────────────────────────────────────────────────────
# Text Chunking
# ─────────────────────────────────────────────────────────────────────────────

def _chunk_text(text: str) -> List[str]:
    chunk_size = settings.CHUNK_SIZE
    overlap = settings.CHUNK_OVERLAP
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# LLM Engine
# ─────────────────────────────────────────────────────────────────────────────

async def _llm_analyze(content: str) -> Optional[List[ExplainabilityMarker]]:
    """
    Runs the LLM analysis pipeline.
    Returns list of markers, or None if LLM is unavailable/failed.
    None signals the caller to use the fallback engine.
    """
    chunks = _chunk_text(content)
    all_markers: List[ExplainabilityMarker] = []
    seen_segments: set[str] = set()

    logger.info(f"[SemanticAnalyzer][LLM] Analyzing {len(chunks)} chunk(s) via Ollama ({settings.LLM_MODEL}).")

    for i, chunk in enumerate(chunks):
        user_prompt = build_analysis_prompt(chunk, i, len(chunks))

        llm_result = await ollama_chat(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        if llm_result is None:
            # LLM failed on this chunk — log and skip (other chunks may still succeed)
            logger.warning(f"[SemanticAnalyzer][LLM] No result for chunk {i + 1}. LLM unavailable or timed out.")
            return None  # Signal full fallback

        chunk_markers = _parse_llm_markers(llm_result, chunk)

        # Deduplicate across chunks by text_segment
        for marker in chunk_markers:
            if marker.text_segment not in seen_segments:
                seen_segments.add(marker.text_segment)
                all_markers.append(marker)

        logger.info(f"[SemanticAnalyzer][LLM] Chunk {i + 1}/{len(chunks)}: {len(chunk_markers)} marker(s).")

    # Sort by confidence descending — most certain flags first
    all_markers.sort(key=lambda m: m.confidence, reverse=True)

    return all_markers


# ─────────────────────────────────────────────────────────────────────────────
# Public Entry Point — Called by Router
# ─────────────────────────────────────────────────────────────────────────────

async def analyze_semantics(content: str) -> List[ExplainabilityMarker]:
    """
    Agent B public interface.
    Tries LLM engine first. Falls back to rule-based on any failure.
    Interface is IDENTICAL to Phase 1 — no changes required upstream.
    """
    try:
        # Attempt LLM analysis
        llm_markers = await _llm_analyze(content)

        if llm_markers is not None:
            logger.info(f"[SemanticAnalyzer] LLM engine returned {len(llm_markers)} marker(s). ✅")
            return llm_markers

        # LLM failed — fall back silently
        logger.info("[SemanticAnalyzer] Falling back to rule-based engine. 🔄")

    except Exception as exc:
        logger.error(f"[SemanticAnalyzer] LLM pipeline error: {exc}", exc_info=True)
        logger.info("[SemanticAnalyzer] Falling back to rule-based engine after exception. 🔄")

    # Rule-based fallback
    try:
        rule_markers = _rule_based_analyze(content)
        logger.info(f"[SemanticAnalyzer] Rule-based engine returned {len(rule_markers)} marker(s).")
        return rule_markers
    except Exception as exc:
        logger.error(f"[SemanticAnalyzer] Rule-based fallback also failed: {exc}", exc_info=True)
        return []
