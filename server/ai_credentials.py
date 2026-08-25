"""Request-scoped customer AI credentials.

Provider keys saved through the BYOK endpoint are decrypted only inside the
request that needs them.  A context variable keeps the credential out of
function signatures and prevents scheduled or public-demo work from
accidentally inheriting a customer's key.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator, Optional

from .auth import decrypt_credentials

logger = logging.getLogger(__name__)

SUPPORTED_CUSTOM_PROVIDERS = frozenset({"openai", "gemini"})


@dataclass(frozen=True)
class AICredentials:
    provider: str
    api_key: str


_active_credentials: ContextVar[Optional[AICredentials]] = ContextVar(
    "kopykat_active_ai_credentials",
    default=None,
)


def get_user_ai_credentials(user) -> Optional[AICredentials]:
    """Return valid Megastore BYOK credentials without exposing the secret.

    A stored ciphertext alone is not enough to activate BYOK.  The account
    must still have the entitlement, the provider must be supported, and the
    ciphertext must decrypt successfully with the current deployment key.
    """

    if getattr(user, "plan", None) != "megastore":
        return None

    provider = (getattr(user, "custom_ai_provider", None) or "").strip().lower()
    encrypted_key = getattr(user, "custom_ai_key_encrypted", None)
    if provider not in SUPPORTED_CUSTOM_PROVIDERS or not encrypted_key:
        return None

    try:
        api_key = decrypt_credentials(encrypted_key).strip()
    except Exception:
        logger.warning("Stored BYOK credential could not be decrypted for user_id=%s", getattr(user, "id", "unknown"))
        return None

    if len(api_key) < 10:
        return None
    return AICredentials(provider=provider, api_key=api_key)


def get_active_ai_credentials() -> Optional[AICredentials]:
    """Return credentials bound to the current request/task, if any."""

    return _active_credentials.get()


@contextmanager
def user_ai_credentials(user) -> Iterator[Optional[AICredentials]]:
    """Bind a user's validated BYOK credentials for one operation only."""

    token = _active_credentials.set(get_user_ai_credentials(user))
    try:
        yield _active_credentials.get()
    finally:
        _active_credentials.reset(token)
