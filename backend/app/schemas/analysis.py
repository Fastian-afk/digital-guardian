from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl


# ─────────────────────────────────────────────────────────────────────────────
# REQUEST SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class AnalysisRequest(BaseModel):
    """
    Payload sent from the Chrome Extension to the /analyze endpoint.
    """
    url: HttpUrl = Field(..., description="Full URL of the page being analyzed.")
    domain: str = Field(..., min_length=1, max_length=253, description="Root domain of the URL.")
    title: str = Field(default="", max_length=512, description="Page <title> tag content.")
    content: str = Field(..., min_length=10, max_length=50000, description="Scraped raw text from the page.")

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://example-news.com/article/123",
                "domain": "example-news.com",
                "title": "Shocking Discovery Changes Everything",
                "content": "Scientists have allegedly proven that the moon is made of cheese..."
            }
        }


# ─────────────────────────────────────────────────────────────────────────────
# RESPONSE SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class ExplainabilityMarker(BaseModel):
    """
    A single flagged segment of text with a reason and confidence score.
    Maps directly to a DOM highlight in the browser extension.
    """
    text_segment: str = Field(..., description="The exact substring flagged in the content.")
    flag_type: str = Field(
        ...,
        description="Category of the flag.",
        examples=["Sensationalism", "Unverified Claim", "Loaded Language", "Logical Fallacy", "AI Hallucination Marker"]
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model confidence in this flag (0.0 – 1.0).")
    explanation: str = Field(..., description="Human-readable XAI explanation for why this segment was flagged.")

    class Config:
        json_schema_extra = {
            "example": {
                "text_segment": "Scientists have allegedly proven",
                "flag_type": "Unverified Claim",
                "confidence": 0.87,
                "explanation": "The word 'allegedly' combined with 'proven' is a logical contradiction commonly used to introduce unsubstantiated claims."
            }
        }


class SourceReputationDetail(BaseModel):
    """
    Detailed output of the Source Verifier agent.
    """
    domain: str
    reputation_label: str = Field(..., description="e.g. 'Reputable', 'Satire', 'Known Misinformation', 'Unknown'")
    reputation_score: int = Field(..., ge=0, le=100, description="Numeric reputation score for the domain.")
    source: str = Field(..., description="Where the reputation data came from: 'local_db' | 'heuristic'")


class TrustPayload(BaseModel):
    """
    The complete, structured output returned to the browser extension.
    This is the core deliverable of the entire pipeline.
    """
    url: str = Field(..., description="The analyzed URL.")
    overall_score: int = Field(..., ge=0, le=100, description="Final composite Trust Score from 0 (Dangerous) to 100 (Verified).")
    risk_level: str = Field(
        ...,
        description="Human-readable risk label derived from overall_score.",
        examples=["VERIFIED", "CAUTION", "HIGH_RISK"]
    )
    domain_reputation: SourceReputationDetail
    markers: List[ExplainabilityMarker] = Field(default_factory=list)
    summary: str = Field(..., description="A 2-3 sentence plain-English summary of the analysis for youth users.")
    cached: bool = Field(default=False, description="True if this result was served from the local cache.")
    analysis_duration_ms: Optional[int] = Field(default=None, description="Time taken for live analysis in milliseconds.")

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://example-news.com/article/123",
                "overall_score": 24,
                "risk_level": "HIGH_RISK",
                "domain_reputation": {
                    "domain": "example-news.com",
                    "reputation_label": "Unknown",
                    "reputation_score": 30,
                    "source": "heuristic"
                },
                "markers": [],
                "summary": "This article contains multiple sensationalist phrases and unverified claims. Exercise caution before sharing.",
                "cached": False,
                "analysis_duration_ms": 1820
            }
        }


class HealthResponse(BaseModel):
    status: str
    version: str
    llm_reachable: bool
    llm_model: Optional[str] = None
    db_status: str
