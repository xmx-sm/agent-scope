

"""
PostgreSQL 入口 _pg：按 function 分流到结构化取数 / 只读 SQL。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。

原实现返回 list | str | dict | None 四态混合（错误返回字符串、未知 function 返回 None），
现统一为信封：错误 → 400，未知 function → 400（原 None 会被入口当成功处理，是隐患）。
"""

from typing import Any, Dict

from ._helper import _check_ident, _err, _ok
from .dialect import _sql_dialect_query, _sql_dialect_table
from .executors import _pg_exec


async def _pg(data: dict = None) -> Dict[str, Any]:
    """PostgreSQL 只读操作分发。

    入参 (data):
        function(str, 必填)  list_databases / list_tables / describe_table /
                            table_data / count_table / run_query
        cfg(dict, 必填)      已归一化的连接配置
        args(dict, 可选)     业务参数（database/pattern/table/sql/limit/offset/filters/...）

    返回: {"code":200, "data": <该 function 的结果>, "message":"success"}
          或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_pg")
    function = data.get("function")
    if not function:
        return _err("缺少 function 字段", "_pg")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_pg")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_pg")
    args = data.get("args")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return _err(f"args 必须是字典，收到 {type(args).__name__}", "_pg")
    db = args.get("database") or cfg.get("database")
    if function == "list_databases":
        rc = await _pg_exec({"cfg": cfg, "database": "postgres",
                             "sql": "select datname from pg_database where not datistemplate order by datname",
                             "fetch": True})
        if rc.get("code") != 200:
            return rc
        return _ok([r[0] for r in rc["data"]["rows"]])
    if function == "list_tables":
        sql = ("select table_schema, table_name from information_schema.tables "
               "where table_schema not in ('pg_catalog','information_schema')")
        a = []
        if args.get("pattern"):
            sql += " and table_name like $" + str(len(a) + 1)
            a.append(args["pattern"])
        if db:
            sql += " and table_catalog = $" + str(len(a) + 1)
            a.append(db)
        sql += " limit 200"
        rc = await _pg_exec({"cfg": cfg, "database": db or cfg.get("database") or "postgres",
                             "sql": sql, "args": a, "fetch": True})
        if rc.get("code") != 200:
            return rc
        return _ok([{"schema": r[0], "table": r[1]} for r in rc["data"]["rows"]])
    if function == "describe_table":
        ci = _check_ident({"name": args.get("table")})
        if ci.get("code") != 200:
            return ci
        rc = await _pg_exec({"cfg": cfg, "database": db,
                             "sql": "select column_name, data_type, is_nullable, column_default from information_schema.columns "
                                    "where table_name = $1 order by ordinal_position",
                             "args": (args["table"].split(".")[-1],), "fetch": True})
        if rc.get("code") != 200:
            return rc
        rows = rc["data"]["rows"]
        if not rows:
            return _err(f"表不存在或无列: {args['table']}", "_pg")
        return _ok([{"column": r[0], "type": r[1], "nullable": r[2], "default": r[3]} for r in rows])
    if function in ("table_data", "count_table"):
        return await _sql_dialect_table({"dialect": "pg", "cfg": cfg, "args": args,
                                         "function": function})
    if function == "run_query":
        return await _sql_dialect_query({"dialect": "pg", "cfg": cfg, "args": args})
    return _err(f"_pg 不支持的 function: {function}", "_pg")
