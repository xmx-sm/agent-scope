"""Agent 输入防注入与输出密钥脱敏。"""

from __future__ import annotations

import json
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.services.config.service import async_get_config

_DEFAULT_INPUT_PATTERNS = [
    r"忽略(以上|之前|前面|先前).{0,12}(指令|规则|约束|提示)",
    r"(无视|绕过|突破|解除).{0,12}(安全|系统|策略|限制|规则|提示词)",
    r"(输出|泄露|告诉我|展示).{0,12}(系统提示词|系统指令|api[_ ]?key|密钥|密码|token)",
    r"ignore\s+(all\s+)?(previous|above|prior)\s+instructions",
    r"disregard\s+(the\s+)?(system|previous)\s+(prompt|instructions)",
    r"reveal\s+(the\s+)?(system\s+prompt|api\s*key|secret|password)",
    r"developer\s+mode|jailbreak|DAN\s+mode",
    r"你现在是.{0,20}(开发者|管理员|超级管理员|无限制)",
]
_SECRET_PATTERNS = [
    (re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{16,}\b"), "[REDACTED_KEY]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}=*\b", re.I), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"(?i)\b(password|passwd|pwd|api[_-]?key|secret|token)\s*[:=]\s*[^\s,;]{6,}"), r"\1=[REDACTED]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[REDACTED_PRIVATE_KEY]"),
]


async def async_guard_input(params: dict) -> dict:
    """检测疑似提示词注入。

    参数：session / text / source
    返回：{"blocked": bool, "warn": bool, "matches": [pattern]}
    """
    session: AsyncSession = params["session"]
    text = str(params.get("text") or "")
    enabled = bool(
        await async_get_config(
            {"session": session, "key": "security.input_guard_enabled", "default": True}
        )
    )
    if not enabled:
        return {"blocked": False, "warn": False, "matches": []}
    action = str(
        await async_get_config(
            {"session": session, "key": "security.input_guard_action", "default": "block"}
        )
        or "block"
    )
    extra_raw = await async_get_config(
        {"session": session, "key": "security.input_guard_patterns", "default": "[]"}
    )
    try:
        extra = json.loads(extra_raw) if isinstance(extra_raw, str) else (extra_raw or [])
    except (ValueError, TypeError):
        extra = []
    patterns = [*_DEFAULT_INPUT_PATTERNS]
    patterns += [str(item) for item in extra if isinstance(item, str) and item.strip()]
    matches = []
    for pattern in patterns:
        try:
            if re.search(pattern, text, re.I | re.S):
                matches.append(pattern)
        except re.error:
            continue
    return {
        "blocked": bool(matches) and action == "block",
        "warn": bool(matches) and action != "block",
        "matches": matches,
    }


def _redact_text(text: str) -> str:
    """脱敏文本中的密钥、Token、密码与私钥。参数：text。"""
    value = str(text or "")
    for pattern, replacement in _SECRET_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def _redact_obj(value):
    """递归脱敏工具返回值中的字符串。参数：value。"""
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, list):
        return [_redact_obj(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_obj(item) for item in value)
    if isinstance(value, dict):
        return {key: _redact_obj(item) for key, item in value.items()}
    return value


__all__ = ["async_guard_input"]
