"""Password hashing and login tokens.

Passwords: only the bcrypt hash is stored; the password itself never is.
Tokens: after login the backend issues a signed JWT; the UI sends it back as `Authorization: Bearer <token>`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import hashlib
import secrets

import bcrypt
import jwt

from backend.config import get_settings

BCRYPT_MAX_BYTES = 72  # bcrypt ignores anything longer, so longer passwords are rejected up front
JWT_ALGORITHM = "HS256"

# Checked when the user name doesn't exist, so a wrong name takes as long as a wrong password
# and response times don't reveal which user names exist.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt()).decode("ascii")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str | None) -> bool:
    ok = bcrypt.checkpw(password.encode("utf-8"), (password_hash or _DUMMY_HASH).encode("ascii"))
    return ok and password_hash is not None


API_KEY_PREFIX = "mcpg_"  # makes gateway keys easy to recognise (e.g. by secret scanners)


def new_api_key() -> tuple[str, str]:
    """A new random gateway API key and its SHA-256 hash. Store only the hash; show the key once.

    A fast unsalted hash is right here (unlike passwords): the key is 256 random bits, so it can't be guessed,
    and the gateway must find a key by its hash (WHERE key_hash = ?).
    """
    key = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return key, hash_api_key(key)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def create_access_token(user_id: int, user_name: str, user_type: str, token_version: int) -> tuple[str, int]:
    """Signed token for a logged-in user, and its lifetime in seconds.

    `ver` is the user's token_version at login; bumping it in the DB (password change) ends every token.
    `jti` is this token's own id; putting it in the revoked-token table (logout) ends just this token.
    """
    s = get_settings()
    now = datetime.now(UTC)
    expires_in = s.jwt_expire_minutes * 60
    claims = {
        "sub": str(user_id),
        "name": user_name,
        "type": user_type,
        "ver": token_version,
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    return jwt.encode(claims, s.jwt_secret, algorithm=JWT_ALGORITHM), expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    """The token's claims; raises jwt.InvalidTokenError if it is forged, malformed or expired."""
    return jwt.decode(token, get_settings().jwt_secret, algorithms=[JWT_ALGORITHM], options={"require": ["sub", "exp", "ver", "jti"]})
