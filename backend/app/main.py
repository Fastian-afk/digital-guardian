from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import get_settings
from app.db.database import init_db
from app.routers.analyze import router as analyze_router
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan (replaces deprecated on_event startup/shutdown)
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    await init_db()
    logger.info("✅ Database initialized. Server ready.")
    yield
    logger.info("🛑 Shutting down Digital Guardian API.")


# ─────────────────────────────────────────────────────────────────────────────
# App Instance
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "**Digital Guardian** — A sovereign, privacy-first AI Trust Layer for the web. "
        "Analyzes digital content for misinformation, hallucinations, and bias. "
        "Built for the UNESCO MIL Youth Hackathon."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ─────────────────────────────────────────────────────────────────────────────
# CORS — Must allow chrome-extension:// origins
# ─────────────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Route Registration
# ─────────────────────────────────────────────────────────────────────────────

app.include_router(analyze_router, prefix="/api/v1")


# ─────────────────────────────────────────────────────────────────────────────
# Root Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", tags=["System"], summary="Root ping")
async def root():
    return {
        "project": "Digital Guardian",
        "status": "operational",
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }
