"""
Agent C: Synthesizer
────────────────────
Compiles outputs from Agent A (Source Verifier) and Agent B (Semantic Analyzer)
into a final TrustPayload with a composite Trust Score and plain-English summary.

Scoring Algorithm:
  - Domain Reputation contributes 40% of the final score.
  - Semantic Analysis contributes 60% (penalizes for each marker, weighted by confidence).
  - Final score is clamped to [0, 100].
"""
from typing import List
from app.schemas.analysis import ExplainabilityMarker, SourceReputationDetail, TrustPayload
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Weight constants
_DOMAIN_WEIGHT = 0.40
_SEMANTIC_WEIGHT = 0.60

# Penalty per marker (scaled by confidence), capped at 60 total semantic deduction
_PENALTY_PER_MARKER = 8.0
_MAX_SEMANTIC_PENALTY = 60.0


def _derive_risk_level(score: int) -> str:
    if score >= 70:
        return "VERIFIED"
    elif score >= 40:
        return "CAUTION"
    else:
        return "HIGH_RISK"


def _generate_summary(
    score: int,
    risk_level: str,
    domain_rep: SourceReputationDetail,
    markers: List[ExplainabilityMarker],
) -> str:
    """
    Generates a 2-3 sentence plain-English summary for youth users.
    Adapts language based on risk level.
    """
    domain_part = f"The source domain '{domain_rep.domain}' is rated as '{domain_rep.reputation_label}' ({domain_rep.reputation_score}/100)."

    if risk_level == "VERIFIED":
        marker_part = (
            f"No significant warning signals were detected in the content."
            if not markers
            else f"A few minor signals were detected ({len(markers)} flag(s)), but the overall content appears trustworthy."
        )
        action_part = "This content appears reliable, but always read critically."

    elif risk_level == "CAUTION":
        flag_types = list({m.flag_type for m in markers})
        flag_str = ", ".join(flag_types[:3]) if flag_types else "mixed signals"
        marker_part = f"The content contains {len(markers)} warning signal(s) including: {flag_str}."
        action_part = "Verify key claims with a trusted primary source before sharing."

    else:  # HIGH_RISK
        flag_types = list({m.flag_type for m in markers})
        flag_str = ", ".join(flag_types[:3]) if flag_types else "multiple red flags"
        marker_part = f"Significant red flags detected ({len(markers)} signal(s)): {flag_str}."
        action_part = "Exercise extreme caution. Do not share this content without independent verification."

    return f"{domain_part} {marker_part} {action_part}"


def synthesize(
    url: str,
    domain_reputation: SourceReputationDetail,
    markers: List[ExplainabilityMarker],
    analysis_duration_ms: int | None = None,
    cached: bool = False,
) -> TrustPayload:
    """
    Agent C entry point.
    Computes composite Trust Score and assembles the final TrustPayload.
    """
    try:
        # --- Domain score contribution ---
        domain_contribution = domain_reputation.reputation_score * _DOMAIN_WEIGHT

        # --- Semantic penalty contribution ---
        # Each marker penalizes, scaled by its confidence. Total capped.
        total_penalty = sum(
            min(_PENALTY_PER_MARKER * m.confidence, _PENALTY_PER_MARKER)
            for m in markers
        )
        total_penalty = min(total_penalty, _MAX_SEMANTIC_PENALTY)

        # Semantic score starts at 100 and subtracts penalties
        semantic_score = max(0.0, 100.0 - total_penalty)
        semantic_contribution = semantic_score * _SEMANTIC_WEIGHT

        # --- Final composite score ---
        final_score = int(round(domain_contribution + semantic_contribution))
        final_score = max(0, min(100, final_score))

        risk_level = _derive_risk_level(final_score)

        summary = _generate_summary(final_score, risk_level, domain_reputation, markers)

        logger.info(
            f"[Synthesizer] URL={url} | DomainScore={domain_reputation.reputation_score} "
            f"| Markers={len(markers)} | FinalScore={final_score} | Risk={risk_level}"
        )

        return TrustPayload(
            url=str(url),
            overall_score=final_score,
            risk_level=risk_level,
            domain_reputation=domain_reputation,
            markers=markers,
            summary=summary,
            cached=cached,
            analysis_duration_ms=analysis_duration_ms,
        )

    except Exception as exc:
        logger.error(f"[Synthesizer] Failed to synthesize results for {url}: {exc}", exc_info=True)
        # Return a safe "Unknown" payload rather than crashing
        return TrustPayload(
            url=str(url),
            overall_score=50,
            risk_level="CAUTION",
            domain_reputation=domain_reputation,
            markers=[],
            summary="Analysis encountered an internal error. Results are inconclusive. Please verify manually.",
            cached=False,
            analysis_duration_ms=analysis_duration_ms,
        )
