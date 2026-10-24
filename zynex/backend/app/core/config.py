"""Application configuration in two layers.

1. Environment (backend/.env): only what the server needs *before* it can reach the database, plus secrets.
2. Database (Settings page): everything else. See app/core/settings_registry.py for the full list.

Code keeps reading `settings.SOMETHING`; the proxy below answers from the right layer:
   test override  >  value saved on the Settings page  >  registry default  >  environment field
"""
import os
from typing import Any, Dict, List

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core import settings_registry as registry

_here = os.path.dirname(__file__)
_env_path = os.path.abspath(os.path.join(_here, "..", "..", ".env"))   # backend/.env

DEV_DATABASE_URL = "postgresql+asyncpg://zynex:zynex@localhost:5432/zynex"


class EnvSettings(BaseSettings):
    """Bootstrap values. Anything not listed here is managed on the Settings page."""
    model_config = SettingsConfigDict(env_file=_env_path, extra="ignore")

    ENVIRONMENT: str = "development"          # development | production
    DATABASE_URL: str = DEV_DATABASE_URL
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    UPLOAD_DIR: str = "./uploads"
    # Tender Tiger documents folder (the downloader's TT_DOCS_DIR). Optional: only needed when this server sees that folder
    # at a different path than the downloader recorded (e.g. a mounted share).
    TENDER_DOCS_DIR: str = ""
    # Tender Tiger remote downloader service (e.g. http://10.10.10.19:8787). Optional: streams files directly from the server folder.
    TT_SERVICE_URL: str = ""
    TT_SERVICE_TOKEN: str = ""
    CORS_ORIGINS: str = "http://localhost:3000"   # comma separated; the browser origins that may call the API
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    NVIDIA_API_KEY: str = ""                      # secret: only needed when the AI provider is set to nvidia

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def _production_must_be_configured(self):
        if self.ENVIRONMENT == "development":
            return self
        problems = []
        if len(self.SECRET_KEY) < 32 or self.SECRET_KEY.startswith(("change-me", "dev-secret")):
            problems.append('SECRET_KEY is weak or a placeholder (python -c "import secrets; print(secrets.token_urlsafe(48))")')
        if self.DATABASE_URL == DEV_DATABASE_URL:
            problems.append("DATABASE_URL is still the development default")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self


class LayeredSettings:
    """`settings.X` for env fields and Settings-page fields alike (see module docstring)."""

    def __init__(self, env: EnvSettings):
        object.__setattr__(self, "_env", env)
        object.__setattr__(self, "_saved", {})       # attr -> value saved on the Settings page
        object.__setattr__(self, "_overrides", {})   # attr -> value forced by tests

    # ---- reads
    def __getattr__(self, name: str) -> Any:
        overrides = object.__getattribute__(self, "_overrides")
        if name in overrides:
            return overrides[name]
        saved = object.__getattribute__(self, "_saved")
        if name in saved:
            return saved[name]
        defn = registry.BY_ATTR.get(name)
        if defn is not None:
            return defn.default
        return getattr(object.__getattribute__(self, "_env"), name)

    # ---- test overrides (monkeypatch.setattr works through these)
    def __setattr__(self, name: str, value: Any) -> None:
        self._overrides[name] = value

    def __delattr__(self, name: str) -> None:
        self._overrides.pop(name, None)

    # ---- Settings page values
    def apply_saved(self, values_by_key: Dict[str, Any]) -> None:
        """Replace the saved layer with {registry key: value} loaded from the database."""
        saved = {}
        for key, value in values_by_key.items():
            defn = registry.BY_KEY.get(key)
            if defn is not None:
                saved[defn.attr] = value
        object.__setattr__(self, "_saved", saved)

    def snapshot(self) -> Dict[str, Any]:
        """The Settings-page layer as {attribute: value}, to hand to a worker process (which has no database session)."""
        return dict(object.__getattribute__(self, "_saved"))

    def load_snapshot(self, snap: Dict[str, Any]) -> None:
        object.__setattr__(self, "_saved", dict(snap))

    def saved_keys(self) -> List[str]:
        return [registry.BY_ATTR[a].key for a in self._saved if a in registry.BY_ATTR]

    @property
    def env(self) -> EnvSettings:
        return object.__getattribute__(self, "_env")


settings = LayeredSettings(EnvSettings())
