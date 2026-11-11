"""Configuration from environment (.env in development)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)


class Settings:
    def __init__(self) -> None:
        # Fail closed: ohne explizites ENV=development gelten die Produktionsregeln (keine Dev-Secrets).
        self.ENV = os.getenv("ENV", "production")
        self.DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://fanchat_app:fanchat_app@localhost:5432/fanchat")
        self.MIGRATION_DATABASE_URL = os.getenv(
            "MIGRATION_DATABASE_URL", "postgresql+psycopg2://nexussaas:nexussaas@localhost:5432/fanchat")
        self.APP_DB_PASSWORD = os.getenv("APP_DB_PASSWORD", "fanchat_app")
        self.SECRET_KEY = os.getenv("SECRET_KEY", "")
        self.ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
        # Fans must always be able to tell that a reply was AI-assisted (EU AI Act Art. 50).
        self.AI_DISCLOSURE = os.getenv("AI_DISCLOSURE", "🤖 KI-unterstützte Nachricht, von {model} freigegeben")
        self.LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")  # gemini | anthropic | openai | fake
        secrets_dir = Path.home() / ".secrets"
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        self.ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
        self.ANTHROPIC_API_KEY_FILE = os.getenv("ANTHROPIC_API_KEY_FILE", str(secrets_dir / "anthropic_api_key"))
        self.ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5")
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        self.OPENAI_API_KEY_FILE = os.getenv("OPENAI_API_KEY_FILE", str(secrets_dir / "openai_api_key"))
        self.OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.GEMINI_API_KEY_FILE = os.getenv("GEMINI_API_KEY_FILE", str(Path.home() / ".secrets" / "gemini_api_key"))
        self.FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "")
        self.AUTH_RATE_PER_MINUTE = int(os.getenv("AUTH_RATE_PER_MINUTE", "20"))  # login/register per client IP
        self.STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
        self.STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        self.STRIPE_PRICE_PRO = os.getenv("STRIPE_PRICE_PRO", "")
        self.STRIPE_PRICE_AGENCY = os.getenv("STRIPE_PRICE_AGENCY", "")
        self.PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
        # Uploaded portal exports live here, one sub-directory per tenant; never user-supplied paths.
        self.EXPORT_DIR = os.getenv("EXPORT_DIR", str(ROOT / "var" / "exports"))
        if not self.SECRET_KEY:
            if self.ENV not in ("development", "test"):
                raise RuntimeError("SECRET_KEY required")
            self.SECRET_KEY = "dev-only-insecure-secret-key-change-me-0123456789"
        if not self.FIELD_ENCRYPTION_KEY:
            if self.ENV not in ("development", "test"):
                raise RuntimeError("FIELD_ENCRYPTION_KEY required")
            self.FIELD_ENCRYPTION_KEY = "ZGV2LW9ubHktZmllbGQta2V5LWNoYW5nZS1tZS0xMjM="  # dev only


settings = Settings()
