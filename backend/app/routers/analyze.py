"""
Router: /api/v1/analyze
────────────────────────
Handles inbound analysis requests from the Chrome Extension.
Orchestrates the three-agent pipeline and manages the URL cache.
"""
import json
import time
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.schemas.analysis import AnalysisRequest, TrustPayload, HealthResponse
from app.db.database import get_db, AnalyzedURL
from app.agents.source_verifier import verify_source
from app.agents.semantic_analyzer import analyze_semantics
from app.agents.synthesizer import synthesize
from app.llm.client import check_ollama_health
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter()

# Cache TTL: 6 hours (in seconds). Results older than this are re-analyzed.
_CACHE_TTL_SECONDS = 6 * 60 * 60


# ─────────────────────────────────────────────────────────────────────────────
# POST /analyze — Main Analysis Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/analyze",
    response_model=TrustPayload,
    status_code=status.HTTP_200_OK,
    summary="Analyze a web page for misinformation",
    description=(
        "Accepts a URL and its extracted text content from the browser extension. "
        "Runs the multi-agent trust analysis pipeline and returns a structured TrustPayload "
        "with a Trust Score, explainability markers, and a plain-English summary."
    ),
    tags=["Analysis"],
)
async def analyze_content(
    payload: AnalysisRequest,
    db: AsyncSession = Depends(get_db),
) -> TrustPayload:
    url_str = str(payload.url)
    logger.info(f"[/analyze] Received request for URL: {url_str}")

    # ── Step 1: Check Cache ──────────────────────────────────────────────────
    try:
        cached_result = await _get_cached_result(url_str, db)
        if cached_result:
            logger.info(f"[/analyze] Cache HIT for {url_str}. Returning cached result.")
            return cached_result
    except Exception as exc:
        logger.warning(f"[/analyze] Cache lookup failed (non-fatal): {exc}")

    # ── Step 2: Run Multi-Agent Pipeline ────────────────────────────────────
    start_time = time.monotonic()

    domain_reputation = await verify_source(payload.domain, db)
    markers = await analyze_semantics(payload.content)

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    trust_payload = synthesize(
        url=url_str,
        domain_reputation=domain_reputation,
        markers=markers,
        analysis_duration_ms=elapsed_ms,
        cached=False,
    )

    # ── Step 3: Write to Cache ───────────────────────────────────────────────
    try:
        await _cache_result(url_str, payload.domain, trust_payload, db)
    except Exception as exc:
        logger.warning(f"[/analyze] Failed to write cache (non-fatal): {exc}")

    logger.info(f"[/analyze] Analysis complete. Score={trust_payload.overall_score}, Risk={trust_payload.risk_level}, Time={elapsed_ms}ms")
    return trust_payload


# ─────────────────────────────────────────────────────────────────────────────
# GET /health — Liveness Check
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Backend health check",
    tags=["System"],
)
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    # DB check
    db_ok = "ok"
    try:
        await db.execute(select(AnalyzedURL).limit(1))
    except Exception as exc:
        logger.error(f"[/health] DB check failed: {exc}")
        db_ok = f"error: {str(exc)}"

    # LLM check — non-blocking, 3s timeout
    llm_ok = await check_ollama_health()

    return HealthResponse(
        status="online",
        version=settings.APP_VERSION,
        llm_reachable=llm_ok,
        llm_model=settings.LLM_MODEL if llm_ok else None,
        db_status=db_ok,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Cache Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _get_cached_result(url: str, db: AsyncSession) -> TrustPayload | None:
    """Fetches a cached TrustPayload from the DB if it exists and is within TTL."""
    from datetime import datetime, timezone, timedelta

    stmt = select(AnalyzedURL).where(AnalyzedURL.url == url)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if record is None:
        return None

    # TTL check
    age = datetime.now(timezone.utc) - record.updated_at.replace(tzinfo=timezone.utc)
    if age.total_seconds() > _CACHE_TTL_SECONDS:
        logger.info(f"[Cache] Record for {url} is stale ({age}). Will re-analyze.")
        return None

    from app.schemas.analysis import SourceReputationDetail, ExplainabilityMarker
    domain_rep = SourceReputationDetail(**json.loads(record.domain_reputation_json))
    markers = [ExplainabilityMarker(**m) for m in json.loads(record.markers_json)]

    return TrustPayload(
        url=record.url,
        overall_score=record.overall_score,
        risk_level=record.risk_level,
        domain_reputation=domain_rep,
        markers=markers,
        summary=record.summary,
        cached=True,
        analysis_duration_ms=record.analysis_duration_ms,
    )


async def _cache_result(url: str, domain: str, payload: TrustPayload, db: AsyncSession) -> None:
    """Upserts a TrustPayload into the analyzed_urls cache table."""
    from datetime import datetime, timezone
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    stmt = sqlite_insert(AnalyzedURL).values(
        url=url,
        domain=domain,
        overall_score=payload.overall_score,
        risk_level=payload.risk_level,
        domain_reputation_json=payload.domain_reputation.model_dump_json(),
        markers_json=json.dumps([m.model_dump() for m in payload.markers]),
        summary=payload.summary,
        analysis_duration_ms=payload.analysis_duration_ms,
        updated_at=datetime.now(timezone.utc),
    ).on_conflict_do_update(
        index_elements=["url"],
        set_={
            "overall_score": payload.overall_score,
            "risk_level": payload.risk_level,
            "domain_reputation_json": payload.domain_reputation.model_dump_json(),
            "markers_json": json.dumps([m.model_dump() for m in payload.markers]),
            "summary": payload.summary,
            "analysis_duration_ms": payload.analysis_duration_ms,
            "updated_at": datetime.now(timezone.utc),
        },
    )
    await db.execute(stmt)
    await db.commit()
    logger.debug(f"[Cache] Upserted result for {url}")
