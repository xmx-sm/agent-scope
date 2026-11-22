"""服务端身份锁定：模型参数不能覆盖身份与内部闸门键。"""

from typing import Any


def drop_reserved(params: Any) -> dict:
    out = dict(params or {})
    for key in [
        item
        for item in out
        if item == "user_id" or (isinstance(item, str) and item.startswith("_"))
    ]:
        out.pop(key, None)
    return out


def merge_identity(identity: dict, params: Any) -> dict:
    merged = drop_reserved(params)
    merged.update(identity or {})
    return merged
