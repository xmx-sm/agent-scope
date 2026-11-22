"""服务端身份锁定：模型参数不能覆盖身份与内部闸门键。"""

from typing import Any


def drop_reserved(params: dict) -> dict:
    """丢弃模型传入的身份与内部保留键。参数：params。"""
    out = dict(params.get("params") or {})
    for key in [
        item
        for item in out
        if item == "user_id" or (isinstance(item, str) and item.startswith("_"))
    ]:
        out.pop(key, None)
    return out


def merge_identity(params: dict) -> dict:
    """合并服务端身份与模型参数，身份优先。参数：identity / params。"""
    merged = drop_reserved({"params": params.get("params") or {}})
    merged.update(params.get("identity") or {})
    return merged
