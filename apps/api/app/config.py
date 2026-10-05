from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]
WARSAW = ZoneInfo("Europe/Warsaw")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://dom:change-this-local-password@localhost:5434/dom"
    web_origin: str = "http://localhost:3000"
    receipt_storage: str = str(ROOT / "data/receipts")
    receipt_provider: Literal["manual", "fixture", "openai", "gemini"] = "manual"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    gemini_api_key: str = ""
    gemini_model: str = Field(default="gemini-3.1-flash-lite", pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
    classification_auto_threshold: float = Field(default=0.9, ge=0, le=1)
    classification_review_threshold: float = Field(default=0.6, ge=0, le=1)
    demo_password: str = ""

    @property
    def receipt_ai_available(self) -> bool:
        return bool(
            (self.receipt_provider == "openai" and self.openai_api_key.strip())
            or (self.receipt_provider == "gemini" and self.gemini_api_key.strip())
        )

    @model_validator(mode="after")
    def valid_config(self):
        storage = Path(self.receipt_storage)
        if not storage.is_absolute():
            self.receipt_storage = str(ROOT / storage)
        if self.classification_review_threshold >= self.classification_auto_threshold:
            raise ValueError("Review threshold must be below auto threshold")
        if self.app_env == "production" and (self.receipt_provider == "fixture" or not self.web_origin.startswith("https://")):
            raise ValueError("Production requires HTTPS and a real/manual receipt provider")
        return self


settings = Settings()
