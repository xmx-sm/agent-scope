"""机器人凭据加密。"""

import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import settings


def _fernet() -> Fernet:
    """从独立密钥或 JWT 密钥派生 Fernet 密钥。"""
    source = settings.bot_credential_key or settings.jwt_secret
    key = base64.urlsafe_b64encode(hashlib.sha256(source.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    """加密机器人凭据。"""
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    """解密机器人凭据。"""
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
