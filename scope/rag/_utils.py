# -*- coding: utf-8 -*-
"""RAG 内部参数校验辅助。"""

from __future__ import annotations

from typing import Any, Dict


def as_dict(value: Any, name: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} 必须是字典，收到 {type(value).__name__}")
    return value


def as_bool(value: Any, name: str, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("1", "true", "yes", "on", "y"):
            return True
        if s in ("0", "false", "no", "off", "n", ""):
            return False
    raise ValueError(f"{name} 必须是布尔值（true/false），收到 {value!r}")


__all__ = ["as_dict", "as_bool"]
