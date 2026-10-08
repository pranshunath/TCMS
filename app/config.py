"""Configuration management for trigger-service."""
import os
from typing import List
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()


class Settings(BaseModel):
    REPORTING_HOST: str = Field(default_factory=lambda: os.getenv("REPORTING_HOST", "127.0.0.1"))
    REPORTING_PORT: int = Field(default_factory=lambda: int(os.getenv("REPORTING_PORT", "3307")))
    REPORTING_USER: str = Field(default_factory=lambda: os.getenv("REPORTING_USER", "root"))
    REPORTING_PASSWORD: str = Field(default_factory=lambda: os.getenv("REPORTING_PASSWORD", ""))
    REPORTING_DB: str = Field(default_factory=lambda: os.getenv("REPORTING_DB", "trigger_service"))
    TRIGGER_DEV_AUTH: bool = Field(
        default_factory=lambda: os.getenv("TRIGGER_DEV_AUTH", "false").lower() in ("true", "1", "yes")
    )
    TCMS_ADMINS: str = Field(default_factory=lambda: os.getenv("TCMS_ADMINS", ""))
    CANCEL_ADMINS: str = Field(default_factory=lambda: os.getenv("CANCEL_ADMINS", ""))
    K8S_NAMESPACE: str = Field(default_factory=lambda: os.getenv("K8S_NAMESPACE", "rewards-test"))

    def get_tcms_admins(self) -> List[str]:
        if not self.TCMS_ADMINS:
            return []
        return [email.strip().lower() for email in self.TCMS_ADMINS.split(",") if email.strip()]

    def get_cancel_admins(self) -> List[str]:
        if not self.CANCEL_ADMINS:
            return []
        return [email.strip().lower() for email in self.CANCEL_ADMINS.split(",") if email.strip()]


# Cached singleton instance
_settings = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
