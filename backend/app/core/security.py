"""密码哈希与 JWT。"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.config import settings

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def hash_password(password: str) -> str:
    """scrypt 哈希，格式：scrypt$n$r$p$salt_hex$hash_hex。"""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, hash_hex = stored.split("$")
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(hash_hex)),
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def create_token(
    user_id: str,
    role: str,
    token_type: str = "access",
    expires_minutes: int | None = None,
    jti: str | None = None,
    family_id: str | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    if token_type == "refresh":
        expire = now + timedelta(days=settings.refresh_token_expire_days)
    else:
        expire = now + timedelta(
            minutes=expires_minutes or settings.access_token_expire_minutes
        )
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": expire,
    }
    if jti is not None:
        payload["jti"] = jti
    if family_id is not None:
        payload["fid"] = family_id
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload
