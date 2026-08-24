"""Centralized, environment-aware application configuration.

The application is intentionally usable without a full local secrets file, but
staging and production must never silently fall back to source-controlled
credentials.  Local/test ephemeral values are process-local and are only a
convenience for development; they are not suitable for persistent data.
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Iterable

from cryptography.fernet import Fernet
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load local configuration without overriding values supplied by the process
# manager, CI, or a container orchestrator.
load_dotenv(override=False)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


ENVIRONMENT = (
    os.getenv("ENVIRONMENT")
    or os.getenv("APP_ENV")
    or "development"
).strip().lower()
TESTING = ENVIRONMENT in {"test", "testing"} or _truthy(os.getenv("TESTING"))
STRICT_CONFIG = not TESTING and ENVIRONMENT in {"production", "prod", "staging"}


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or normalized.startswith(("replace_with_", "change_me", "changeme"))


def _secret(name: str, *, minimum_length: int) -> str:
    value = os.getenv(name, "").strip()
    if _is_placeholder(value) or len(value) < minimum_length:
        if STRICT_CONFIG:
            raise RuntimeError(
                f"{name} must be configured with at least {minimum_length} characters "
                f"when ENVIRONMENT={ENVIRONMENT!r}."
            )
        logger.warning("%s is not configured; using an ephemeral development value", name)
        return secrets.token_urlsafe(max(32, minimum_length))
    return value


JWT_SECRET_KEY = _secret("JWT_SECRET_KEY", minimum_length=32)

_configured_fernet_key = os.getenv("INTEGRATION_ENCRYPTION_KEY", "").strip()
try:
    if _is_placeholder(_configured_fernet_key):
        raise ValueError("missing Fernet key")
    # Validate the key format at startup instead of discovering it on the first
    # attempt to save or read an integration.
    Fernet(_configured_fernet_key.encode())
    INTEGRATION_ENCRYPTION_KEY = _configured_fernet_key
except (ValueError, TypeError):
    if STRICT_CONFIG:
        raise RuntimeError(
            "INTEGRATION_ENCRYPTION_KEY must be a valid Fernet key when "
            f"ENVIRONMENT={ENVIRONMENT!r}."
        ) from None
    logger.warning("INTEGRATION_ENCRYPTION_KEY is not configured; using an ephemeral development key")
    INTEGRATION_ENCRYPTION_KEY = Fernet.generate_key().decode()


ADMIN_SECRET = os.getenv("ADMIN_SECRET", "").strip()
if STRICT_CONFIG and (_is_placeholder(ADMIN_SECRET) or len(ADMIN_SECRET) < 24):
    raise RuntimeError(
        "ADMIN_SECRET must be configured with at least 24 characters when "
        f"ENVIRONMENT={ENVIRONMENT!r}."
    )

PUBLIC_BASE_URL = (
    os.getenv("APP_BASE_URL")
    or os.getenv("BASE_URL")
    or ("https://snapcopy-ai.onrender.com" if STRICT_CONFIG else "http://localhost:8000")
).strip().rstrip("/")
if STRICT_CONFIG and not PUBLIC_BASE_URL.startswith("https://"):
    raise RuntimeError("APP_BASE_URL or BASE_URL must use HTTPS in strict environments.")


def env_list(name: str, default: Iterable[str]) -> list[str]:
    """Read a comma-separated environment value while dropping empty items."""

    raw = os.getenv(name)
    values = raw.split(",") if raw is not None else list(default)
    return [value.strip() for value in values if value.strip()]


def env_float(name: str, default: float, *, minimum: float = 0.0, maximum: float = 1.0) -> float:
    """Parse a bounded float, falling back safely for malformed local config."""

    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(maximum, max(minimum, value))


def env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    """Parse a bounded integer used for operational settings."""

    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(maximum, max(minimum, value))
