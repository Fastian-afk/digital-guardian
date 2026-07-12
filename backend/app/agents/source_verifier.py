"""
Agent A: Source Verifier
───────────────────────
Queries the local SQLite domain_reputation table.
Falls back to heuristic scoring if the domain is not in the DB.
Returns a SourceReputationDetail object.
"""
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import DomainReputation
from app.schemas.analysis import SourceReputationDetail
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Heuristic signals for unknown domains
# ─────────────────────────────────────────────────────────────────────────────

_SUSPICIOUS_PATTERNS = [
    r"truth",      # "realtruth.news", "truthfeed.com"
    r"patriot",    # "patriotpost.com"
    r"freedom",    # "freedomjournal.net"
    r"breaking",   # "breakingnewsdaily.biz"
    r"alert",
    r"shocker",
    r"viral",
    r"secret",
]

_TRUSTED_TLDS = {".edu", ".gov", ".org", ".int"}
_SUSPICIOUS_TLDS = {".biz", ".click", ".xyz", ".buzz", ".info"}


def _heuristic_score(domain: str) -> SourceReputationDetail:
    """
    Scores a domain with no DB record using structural heuristics.
    Not a replacement for real data — used as a conservative fallback.
    """
    score = 50  # neutral baseline

    lower = domain.lower()

    # TLD-based adjustments
    for tld in _TRUSTED_TLDS:
        if lower.endswith(tld):
            score += 20
            break

    for tld in _SUSPICIOUS_TLDS:
        if lower.endswith(tld):
            score -= 25
            break

    # Keyword-based adjustments
    for pattern in _SUSPICIOUS_PATTERNS:
        if re.search(pattern, lower):
            score -= 10

    # Penalize excessive subdomains (e.g., news.real.truth.biz)
    parts = lower.split(".")
    if len(parts) > 3:
        score -= 10

    score = max(0, min(100, score))

    label = "Unknown"
    if score >= 70:
        label = "Likely Credible"
    elif score < 35:
        label = "Likely Low Credibility"

    return SourceReputationDetail(
        domain=domain,
        reputation_label=label,
        reputation_score=score,
        source="heuristic",
    )


async def verify_source(domain: str, db: AsyncSession) -> SourceReputationDetail:
    """
    Agent A entry point.
    1. Queries local DB for an exact domain match.
    2. Falls back to heuristic scoring if not found.
    """
    try:
        # Normalize domain (strip www.)
        normalized = domain.lower().strip()
        if normalized.startswith("www."):
            normalized = normalized[4:]

        stmt = select(DomainReputation).where(DomainReputation.domain == normalized)
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()

        if record:
            logger.info(f"[SourceVerifier] DB hit for domain: {normalized} → {record.reputation_label} ({record.reputation_score})")
            return SourceReputationDetail(
                domain=record.domain,
                reputation_label=record.reputation_label,
                reputation_score=record.reputation_score,
                source="local_db",
            )

        logger.info(f"[SourceVerifier] No DB record for '{normalized}'. Running heuristic fallback.")
        return _heuristic_score(normalized)

    except Exception as exc:
        logger.error(f"[SourceVerifier] Error verifying domain '{domain}': {exc}", exc_info=True)
        # Return a safe neutral result instead of crashing
        return SourceReputationDetail(
            domain=domain,
            reputation_label="Unknown",
            reputation_score=50,
            source="error_fallback",
        )
