from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # --- App ---
    APP_NAME: str = "Digital Guardian API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # --- Server ---
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # --- CORS ---
    # Chrome extensions use chrome-extension:// scheme, so we allow all origins locally.
    ALLOWED_ORIGINS: list[str] = ["*"]

    # --- Database ---
    DATABASE_URL: str = "sqlite+aiosqlite:///./digital_guardian.db"

    # --- LLM (Groq API) ---
    GROQ_API_KEY: str = ""                        # Set this in .env
    LLM_BASE_URL: str = "https://api.groq.com"   # Kept for reference
    LLM_MODEL: str = "llama-3.3-70b-versatile"   # Best free Groq model
    LLM_TIMEOUT: int = 30                         # seconds

    # --- Analysis ---
    MAX_CONTENT_CHARS: int = 50000
    CHUNK_SIZE: int = 2000     # chars per chunk sent to LLM
    CHUNK_OVERLAP: int = 200   # overlap between chunks

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
