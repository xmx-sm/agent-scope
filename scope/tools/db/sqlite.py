

"""
SQLite 入口 _lite：结构化取数 / 只读 SQL；list_databases 枚举文件夹模式下的库文件。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。

原实现返回 list | str | dict | None 四态混合，现统一为信封
（未知 function 原返回 None 会被入口当成功处理，现改 400）。
"""

import asyncio
from typing import Any, Dict

from ._helper import _check_ident, _err, _ok, _sqlite_databases
from .dialect import _sql_dialect_query, _sql_dialect_table
from .executors import _lt_exec


async def _lite(data: dict = None) -> Dict[str, Any]:
    """SQLite 只读操作分发。

    入参 (data):
        function(str, 必填)  list_databases / list_tables / describe_table /
                            table_data / count_table / run_query
        cfg(dict, 必填)      已归一化的连接配置（path 或 dir）
        args(dict, 可选)     业务参数（database/pattern/table/sql/...）

    返回: {"code":200, "data": <该 function 的结果>, "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_lite")
    function = data.get("function")
    if not function:
        return _err("缺少 function 字段", "_lite")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_lite")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_lite")
    args = data.get("args")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return _err(f"args 必须是字典，收到 {type(args).__name__}", "_lite")
    if function == "list_databases":
        # _sqlite_databases 是同步纯函数（只列目录），放线程里以免阻塞事件循环
        return await asyncio.to_thread(_sqlite_databases, {"cfg": cfg})
    if function == "list_tables":
        sql = ("select name from sqlite_master "
               "where type in ('table','view') and name not like 'sqlite_%'")
        a = []
        if args.get("pattern"):
            sql += " and name like ?"
            a.append(args["pattern"])
        sql += " order by name limit 200"
        rc = await _lt_exec({"cfg": cfg, "database": args.get("database") or cfg.get("database"),
                             "sql": sql, "args": a, "fetch": True})
        if rc.get("code") != 200:
            return rc
        return _ok([{"schema": "main", "table": r[0]} for r in rc["data"]["rows"]])
    if function == "describe_table":
        t = str(args.get("table") or "").strip()
        ci = _check_ident({"name": t})
        if ci.get("code") != 200:
            return ci
        if "." in t:
            return _err(f"sqlite 无 schema 层级，表名不能含点: {t}", "_lite")
        rc = await _lt_exec({"cfg": cfg, "database": args.get("database") or cfg.get("database"),
                             "sql": f'PRAGMA table_info("{t}")', "fetch": True})
        if rc.get("code") != 200:
            return rc
        rows = rc["data"]["rows"]
        if not rows:
            return _err(f"表不存在或无列: {t}", "_lite")
        return _ok([{"column": r[1], "type": r[2],
                     "nullable": "NO" if r[3] else "YES", "default": r[4],
                     **({"primary_key": True} if r[5] else {})} for r in rows])
    if function in ("table_data", "count_table"):
        return await _sql_dialect_table({"dialect": "sqlite", "cfg": cfg, "args": args,
                                         "function": function})
    if function == "run_query":
        return await _sql_dialect_query({"dialect": "sqlite", "cfg": cfg, "args": args})
    return _err(f"_lite 不支持的 function: {function}", "_lite")
