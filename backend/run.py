"""
run.py — Development server launcher for Digital Guardian API.
Run from the /backend directory: python run.py
"""
import uvicorn
from app.config import get_settings

settings = get_settings()

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,      # Hot-reload on file changes during dev
        log_level="info",
    )
