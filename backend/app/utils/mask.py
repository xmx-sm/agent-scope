"""密钥脱敏与回写哨兵。

配置接口的读-改-写闭环：GET 把密钥替换为 SENTINEL，前端原样提交时代表“未修改”，
写库前还原为库内真值，避免把 ****** 当成真密钥保存。
"""

SENTINEL = "******"


def mask_secret(value):
    """非空标量脱敏；None/空串保持原样。"""
    return SENTINEL if value else value


def is_sentinel(value) -> bool:
    return value == SENTINEL


__all__ = ["SENTINEL", "mask_secret", "is_sentinel"]
