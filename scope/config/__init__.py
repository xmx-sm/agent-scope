# -*- coding: utf-8 -*-
"""scope.config — 默认配置中心（SQLite 存储 + 进程级缓存）。

用法
────
装配 Agent 前预载一次（异步）::

    import scope.config as config
    await config.aload()          # 或首次使用 config.db 时自动建库并灌出厂默认

各域读默认值（同步，走缓存）::

    from scope.config import pick, pick_str, pick_int
    host = pick_str(data.get("smtp_host"), "mail.smtp.host")     # 传入 > sqlite > ""
    verify = pick(data.get("verify"), "net.verify", True)        # 传入(含 False) > sqlite > True
    limit = pick_int(args.get("limit"), "db.table_data.limit", 50)

优先级：调用传入 data > config.db（sqlite） > None/默认。
取到 None 时由各函数原有逻辑决定报错或回落，本层不额外防御。

敏感项（密码/账号）出厂为 None，仅支持部署方手动注入 config.db；
config.db 已列入 .gitignore，绝不入库。
"""

from .merge import pick, pick_int, pick_str
from .store import (
    aget,
    all_values,
    categories,
    clamp_get,
    configure,
    db_path,
    get,
    init_db,
    items_by_category,
    load,
    aload,
    schema_keys,
    set_value,
    unset,
)
from .schema import (
    ALL,
    BY_KEY,
    SECRET_KEYS,
    describe,
    keys_by_category,
)

__all__ = [
    # 生命周期 / 读写
    "configure", "db_path", "init_db", "load", "aload",
    "get", "aget", "set_value", "unset", "all_values",
    # 钳制读取（hard_max 项专用，只收紧不放宽）
    "clamp_get",
    # 合并辅助（各域用这三个）
    "pick", "pick_str", "pick_int",
    # schema 查询
    "ALL", "BY_KEY", "SECRET_KEYS", "describe",
    "categories", "items_by_category", "schema_keys", "keys_by_category",
]
