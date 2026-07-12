from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, String, Integer, Text, DateTime, Float, Boolean
from datetime import datetime, timezone
from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE & SESSION FACTORY
# ─────────────────────────────────────────────────────────────────────────────

engine = create_async_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=settings.DEBUG,
)

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ─────────────────────────────────────────────────────────────────────────────
# BASE MODEL
# ─────────────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# TABLE: analyzed_urls (Cache Layer)
# ─────────────────────────────────────────────────────────────────────────────

class AnalyzedURL(Base):
    """
    Caches analysis results keyed by URL to prevent redundant LLM calls.
    TTL-based invalidation: if updated_at is older than N hours, re-analyze.
    """
    __tablename__ = "analyzed_urls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String(2048), unique=True, nullable=False, index=True)
    domain = Column(String(253), nullable=False, index=True)
    overall_score = Column(Integer, nullable=False)
    risk_level = Column(String(32), nullable=False)
    domain_reputation_json = Column(Text, nullable=False)  # JSON blob
    markers_json = Column(Text, nullable=False)            # JSON blob
    summary = Column(Text, nullable=False)
    analysis_duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ─────────────────────────────────────────────────────────────────────────────
# TABLE: domain_reputation (Source Verifier Local DB)
# ─────────────────────────────────────────────────────────────────────────────

class DomainReputation(Base):
    """
    Local curated database of domain reputation scores.
    Seeded with known reputable and disreputable news sources.
    """
    __tablename__ = "domain_reputation"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain = Column(String(253), unique=True, nullable=False, index=True)
    reputation_label = Column(String(64), nullable=False)   # e.g. "Reputable", "Satire", "Known Misinformation"
    reputation_score = Column(Integer, nullable=False)      # 0-100
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ─────────────────────────────────────────────────────────────────────────────
# DEPENDENCY INJECTION HELPER
# ─────────────────────────────────────────────────────────────────────────────

async def get_db() -> AsyncSession:
    """FastAPI dependency that yields an async DB session."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ─────────────────────────────────────────────────────────────────────────────
# INIT DB — creates tables and seeds domain reputation data
# ─────────────────────────────────────────────────────────────────────────────

SEED_DOMAINS = [
    # REPUTABLE
    {"domain": "reuters.com",       "reputation_label": "Reputable",            "reputation_score": 92, "notes": "International wire service."},
    {"domain": "apnews.com",        "reputation_label": "Reputable",            "reputation_score": 91, "notes": "Associated Press."},
    {"domain": "bbc.com",           "reputation_label": "Reputable",            "reputation_score": 88, "notes": "BBC News."},
    {"domain": "bbc.co.uk",         "reputation_label": "Reputable",            "reputation_score": 88, "notes": "BBC News UK."},
    {"domain": "theguardian.com",   "reputation_label": "Reputable",            "reputation_score": 85, "notes": "UK broadsheet."},
    {"domain": "nytimes.com",       "reputation_label": "Reputable",            "reputation_score": 84, "notes": "New York Times."},
    {"domain": "washingtonpost.com","reputation_label": "Reputable",            "reputation_score": 83, "notes": "Washington Post."},
    {"domain": "who.int",           "reputation_label": "Reputable",            "reputation_score": 95, "notes": "World Health Organization."},
    {"domain": "un.org",            "reputation_label": "Reputable",            "reputation_score": 93, "notes": "United Nations."},
    {"domain": "nature.com",        "reputation_label": "Reputable",            "reputation_score": 97, "notes": "Nature journal, peer-reviewed."},
    {"domain": "sciencemag.org",    "reputation_label": "Reputable",            "reputation_score": 96, "notes": "Science magazine, peer-reviewed."},
    {"domain": "aljazeera.com",     "reputation_label": "Reputable",            "reputation_score": 80, "notes": "Al Jazeera English."},
    {"domain": "dawn.com",          "reputation_label": "Reputable",            "reputation_score": 78, "notes": "Pakistan's leading English newspaper."},
    {"domain": "geo.tv",            "reputation_label": "Reputable",            "reputation_score": 74, "notes": "Geo News Pakistan."},
    # SATIRE
    {"domain": "theonion.com",      "reputation_label": "Satire",               "reputation_score": 50, "notes": "Satirical publication."},
    {"domain": "babylonbee.com",    "reputation_label": "Satire",               "reputation_score": 50, "notes": "Christian satire publication."},
    # KNOWN MISINFORMATION / LOW CREDIBILITY
    {"domain": "naturalnews.com",   "reputation_label": "Known Misinformation", "reputation_score": 8,  "notes": "Repeatedly debunked health misinformation."},
    {"domain": "infowars.com",      "reputation_label": "Known Misinformation", "reputation_score": 5,  "notes": "Conspiracy theories, media bias."},
    {"domain": "beforeitsnews.com", "reputation_label": "Known Misinformation", "reputation_score": 10, "notes": "User-submitted, unvetted content."},
    {"domain": "worldnewsdailyreport.com", "reputation_label": "Known Misinformation", "reputation_score": 5, "notes": "Fabricated news site."},
]


async def init_db() -> None:
    """
    Creates all tables and seeds the domain_reputation table if empty.
    Called once on FastAPI startup.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified.")

    async with AsyncSessionFactory() as session:
        from sqlalchemy import select
        result = await session.execute(select(DomainReputation).limit(1))
        if result.scalar_one_or_none() is None:
            for entry in SEED_DOMAINS:
                session.add(DomainReputation(**entry))
            await session.commit()
            logger.info(f"Seeded {len(SEED_DOMAINS)} domain reputation records.")
        else:
            logger.info("Domain reputation table already seeded. Skipping.")
