

"""
MySQL 入口 _my：按 function 分流到结构化取数 / 只读 SQL。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。

原实现返回 list | str | dict | None 四态混合，现统一为信封
（未知 function 原返回 None 会被入口当成功处理，现改 400）。
"""

from typing import Any, Dict

from ._helper import _check_ident, _err, _ok, eff_list_tables_limit
from .dialect import _sql_dialect_query, _sql_dialect_table
from .executors import _my_exec


async def _my(data: dict = None) -> Dict[str, Any]:
    """MySQL 只读操作分发。

    入参 (data):
        function(str, 必填)  list_databases / list_tables / describe_table /
                            table_data / count_table / run_query
        cfg(dict, 必填)      已归一化的连接配置
        args(dict, 可选)     业务参数

    返回: {"code":200, "data": <该 function 的结果>, "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_my")
    function = data.get("function")
    if not function:
        return _err("缺少 function 字段", "_my")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_my")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_my")
    args = data.get("args")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return _err(f"args 必须是字典，收到 {type(args).__name__}", "_my")
    db = args.get("database") or cfg.get("database")
    if function == "list_databases":
        rc = await _my_exec({"cfg": cfg, "database": None, "sql": "show databases", "fetch": True})
        if rc.get("code") != 200:
            return rc
        return _ok([r[0] for r in rc["data"]["rows"]])
    if function == "list_tables":
        sql = ("select table_schema, table_name from information_schema.tables "
               "where table_schema not in ('information_schema','mysql','performance_schema','sys')")
        a = []
        if args.get("pattern"):
            sql += " and table_name like %s"; a.append(args["pattern"])
        if db:
            sql += " and table_schema = %s"; a.append(db)
        sql += f" limit {eff_list_tables_limit()}"
        rc = await _my_exec({"cfg": cfg, "database": db, "sql": sql, "args": a, "fetch": True})
        if rc.get("code") != 200:
            return rc
        return _ok([{"schema": r[0], "table": r[1]} for r in rc["data"]["rows"]])
    if function == "describe_table":
        ci = _check_ident({"name": args.get("table"), "what": "表名"})
        if ci.get("code") != 200:
            return ci
        t = args["table"]
        sql = ("select column_name, data_type, is_nullable, column_default from information_schema.columns "
               "where table_name = %s")
        a = [t.split(".")[-1]]
        if "." in t:
            sql += " and table_schema = %s"; a.insert(0, t.split(".")[0])
        elif db:
            sql += " and table_schema = %s"; a.append(db)
        sql += " order by ordinal_position"
        rc = await _my_exec({"cfg": cfg, "database": db, "sql": sql, "args": a, "fetch": True})
        if rc.get("code") != 200:
            return rc
        rows = rc["data"]["rows"]
        if not rows:
            return _err(f"表不存在或无列: {t}", "_my")
        return _ok([{"column": r[0], "type": r[1], "nullable": r[2], "default": r[3]} for r in rows])
    if function in ("table_data", "count_table"):
        return await _sql_dialect_table({"dialect": "mysql", "cfg": cfg, "args": args,
                                         "function": function})
    if function == "run_query":
        return await _sql_dialect_query({"dialect": "mysql", "cfg": cfg, "args": args})
    return _err(f"_my 不支持的 function: {function}", "_my")
