"""Password hashing and login tokens.

Passwords: only the bcrypt hash is stored; the password itself never is.
Tokens: after login the backend issues a signed JWT; the UI sends it back as `Authorization: Bearer <token>`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

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


def create_access_token(user_id: int, user_name: str, user_type: str) -> tuple[str, int]:
    """Signed token for a logged-in user, and its lifetime in seconds."""
    s = get_settings()
    now = datetime.now(UTC)
    expires_in = s.jwt_expire_minutes * 60
    claims = {
        "sub": str(user_id),
        "name": user_name,
        "type": user_type,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    return jwt.encode(claims, s.jwt_secret, algorithm=JWT_ALGORITHM), expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    """The token's claims; raises jwt.InvalidTokenError if it is forged, malformed or expired."""
    return jwt.decode(token, get_settings().jwt_secret, algorithms=[JWT_ALGORITHM], options={"require": ["sub", "exp"]})
