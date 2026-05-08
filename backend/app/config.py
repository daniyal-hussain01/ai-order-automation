"""Centralized config (12-factor app style)."""
import os
from typing import List


def _split_csv(value: str) -> List[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings:
    # Core
    APP_ENV: str = os.getenv("APP_ENV", "local")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "/data/orders.sqlite3")
    MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
    CORS_ORIGINS: List[str] = _split_csv(os.getenv("CORS_ORIGINS", "*"))

    # OCR
    TESSERACT_CMD: str = os.getenv("TESSERACT_CMD", "/usr/bin/tesseract")
    OCR_LANG: str = os.getenv("OCR_LANG", "eng")

    # AI parser
    USE_LLM: bool = os.getenv("USE_LLM", "false").lower() == "true"
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

    # Bravo ERP
    BRAVO_API_URL: str = os.getenv("BRAVO_API_URL", "")  # empty = mock mode
    BRAVO_API_KEY: str = os.getenv("BRAVO_API_KEY", "")


settings = Settings()
