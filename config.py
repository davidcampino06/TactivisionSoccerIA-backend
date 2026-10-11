"""Backend configuration loaded from environment variables (never hard-coded secrets)."""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

load_dotenv()
logger = logging.getLogger("tactivision.config")

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173,https://tactivision-frontend.onrender.com"


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value in (None, ""):
        return default
    return raw_value.strip().lower() in ("1", "true", "yes", "on")


def resolve_database_url() -> str | None:
    """Build the SQLAlchemy URL.

    - DATABASE_URL=postgresql://user:password@host/db?sslmode=require   (preferred)
    - NEON_DB_URL + NEON_DB_USERNAME + NEON_DB_PASSWORD                  (current Render setup)
      As in the original prototype, NEON_DB_USERNAME/PASSWORD take priority over any
      credentials written inside NEON_DB_URL.
    A leftover ``jdbc:`` prefix from the old Spring Boot configuration is removed.
    """
    database_url = os.getenv("DATABASE_URL")
    raw_url = database_url or os.getenv("NEON_DB_URL")
    if not raw_url:
        return None
    raw_url = raw_url.strip().strip('"').strip("'").removeprefix("jdbc:")
    if raw_url.startswith("postgres://"):
        raw_url = "postgresql://" + raw_url[len("postgres://"):]
    if raw_url.startswith("postgresql://"):
        raw_url = "postgresql+psycopg2://" + raw_url[len("postgresql://"):]

    url = make_url(raw_url)
    if not database_url:
        username, password = os.getenv("NEON_DB_USERNAME"), os.getenv("NEON_DB_PASSWORD")
        if username:
            url = url.set(username=username)
        if password:
            url = url.set(password=password)
    return url.render_as_string(hide_password=False)


def describe_database_url(database_url: str | None) -> str:
    """Safe description for logs (never includes the password)."""
    if not database_url:
        return "not configured"
    url = make_url(database_url)
    return f"{url.username}@{url.host}:{url.port or 5432}/{url.database}"


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY")
    if secret:
        return secret
    logger.warning("JWT_SECRET_KEY is not set: using a random key (tokens expire on restart).")
    return secrets.token_urlsafe(48)


def _rsa_private_key() -> str | None:
    """PEM private key; a one-line value with literal \\n (as in .env or Render) is accepted."""
    raw = (os.getenv("RSA_PRIVATE_KEY") or "").strip().strip('"').strip("'")
    return raw.replace("\\n", "\n") if raw else None


ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
IS_PRODUCTION = ENVIRONMENT == "production"


@dataclass(frozen=True)
class Settings:
    environment: str = ENVIRONMENT
    # Swagger (/docs) lists every endpoint: it is turned off in production.
    enable_docs: bool = field(default_factory=lambda: _env_bool("ENABLE_DOCS", not IS_PRODUCTION))
    rsa_private_key: str | None = field(default_factory=_rsa_private_key)
    # In production the browser must send passwords encrypted (RSA-OAEP); plain text is rejected.
    require_encrypted_passwords: bool = field(
        default_factory=lambda: _env_bool("REQUIRE_ENCRYPTED_PASSWORDS", IS_PRODUCTION)
    )
    # Row-Level Security in PostgreSQL (TactiSoccerIA-db migration 0002 must be applied first).
    database_rls: bool = field(default_factory=lambda: _env_bool("DATABASE_RLS", False))
    login_max_failed_attempts: int = field(default_factory=lambda: int(os.getenv("LOGIN_MAX_FAILED_ATTEMPTS", "5")))
    login_lock_minutes: int = field(default_factory=lambda: int(os.getenv("LOGIN_LOCK_MINUTES", "15")))
    database_url: str | None = field(default_factory=resolve_database_url)
    jwt_secret_key: str = field(default_factory=_jwt_secret)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = field(
        default_factory=lambda: int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))
    )
    password_reset_expire_minutes: int = field(
        default_factory=lambda: int(os.getenv("PASSWORD_RESET_EXPIRE_MINUTES", "30"))
    )
    # There is no e-mail service yet. Only in development the reset token is returned in the response.
    password_reset_expose_token: bool = field(
        default_factory=lambda: _env_bool("PASSWORD_RESET_EXPOSE_TOKEN", False)
    )
    cors_origins: list[str] = field(
        default_factory=lambda: [
            origin.strip() for origin in os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",") if origin.strip()
        ]
    )
    database_connect_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "10"))
    )
    ai_service_url: str = field(default_factory=lambda: os.getenv("AI_SERVICE_URL", "http://localhost:8001").rstrip("/"))
    ai_service_api_key: str = field(default_factory=lambda: os.getenv("AI_SERVICE_API_KEY", ""))
    ai_service_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("AI_SERVICE_TIMEOUT_SECONDS", "900"))
    )
    upload_dir: Path = field(default_factory=lambda: Path(os.getenv("UPLOAD_DIR", "uploads")))
    max_video_size_mb: int = field(default_factory=lambda: int(os.getenv("MAX_VIDEO_SIZE_MB", "200")))
    allow_simulation_mode: bool = field(default_factory=lambda: _env_bool("ALLOW_SIMULATION_MODE", True))


settings = Settings()
