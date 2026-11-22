

"""
SQL 方言编排层：把 function 语义翻译成具体语句，再交给 executors 执行。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。

_sql_dialect_table  结构化取数（list_tables/describe_table/table_data/count_table）
_sql_dialect_query  只读 SQL（select/with/show/desc/explain 白名单起始词）
_sql_dialect_write  写 SQL（insert/update/delete，拒绝 DDL 与多语句）
本层不建连接，只造语句与整理结果。

原实现的返回类型是 str|dict 混合（校验失败返回错误字符串，由入口 _err 包装），
现统一为信封：校验失败直接返回 400 信封，调用方可 `return r` 转发。

行为修正:
    _sql_dialect_table 的 filters 遇到非法列名，原实现是 `if _check_ident(...): continue`
    —— **静默丢掉该条件照常查询**，调用方拿到的是少了条件的结果集（不是错误）。
    现改为返回 400 报错。order_by 的非法列名原样静默忽略，同样改为报错。
"""


import re
from typing import Any, Dict

from ._helper import (
    _FORBIDDEN_RE,
    _READONLY_RE,
    _WRITE_START_RE,
    _FORBIDDEN_WRITE_RE,
    _check_ident,
    _check_scalars,
    _err,
    _ok,
    _qcol,
    _qtbl,
    _rows_to_dicts,
    _wph,
    _write_where,
    eff_max_rows,
    eff_run_query_limit,
    eff_table_data_limit,
)
from .executors import _lt_exec, _lt_write, _my_exec, _my_write, _pg_exec, _pg_write


async def _sql_dialect_table(data: dict = None) -> Dict[str, Any]:
    """结构化取数的方言编排。

    入参 (data):
        dialect(str, 必填)     pg / mysql / sqlite
        cfg(dict, 必填)        已归一化的连接配置
        args(dict, 可选)       业务参数：table(必填)/database/columns/filters/order_by/offset/limit
        function(str, 必填)    list_tables / describe_table / table_data / count_table

    返回: {"code":200, "data": <该 function 的结果结构>, "message":"success"}
          或 {"code":400, "data": 位置, "message": "错误：<原因>"}
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_sql_dialect_table")
    dialect = data.get("dialect")
    if not dialect:
        return _err("缺少 dialect 字段", "_sql_dialect_table")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_sql_dialect_table")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_sql_dialect_table")
    args = data.get("args")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return _err(f"args 必须是字典，收到 {type(args).__name__}", "_sql_dialect_table")
    function = data.get("function")
    if not function:
        return _err("缺少 function 字段", "_sql_dialect_table")

    table = args.get("table")
    ci = _check_ident({"name": table})
    if ci.get("code") != 200:
        return ci
    db = args.get("database") or cfg.get("database")
    mysql = dialect == "mysql"

    def qcol(name):
        return f"`{name}`" if mysql else f'"{name}"'

    def qtbl(name):
        parts = str(name).split(".")
        return ".".join(qcol(p) for p in parts)

    def ph(i):
        return f"${i}" if dialect == "pg" else ("%s" if mysql else "?")
    cols = args.get("columns") or []
    sel = ", ".join(qcol(c) for c in cols) if cols else "*"
    q = f"select {sel} from {qtbl(table)}"
    where, a, idx = [], [], 1
    for col, val in (args.get("filters") or {}).items():
        ci_col = _check_ident({"name": col, "what": "列名"})
        if ci_col.get("code") != 200:
            return ci_col                     # 原实现是 continue 静默丢条件，现报错
        if isinstance(val, dict):
            op = None
            if "like" in val:
                op, v = "like", val["like"]
            elif "gte" in val:
                op, v = ">=", val["gte"]
            elif "lte" in val:
                op, v = "<=", val["lte"]
            if op:
                where.append(f"{qcol(col)} {op} {ph(idx)}")
                a.append(v)
                idx += 1
            else:
                return _err(f"列 {col} 的条件对象为空，请用等值或 like/gte/lte",
                            "_sql_dialect_table")
            continue
        where.append(f"{qcol(col)} = {ph(idx)}")
        a.append(val)
        idx += 1
    if where:
        q += " where " + " and ".join(where)

    async def run(sql_text, sql_args, want_fetch=True):
        payload = {"cfg": cfg, "database": db, "sql": sql_text, "args": sql_args,
                   "fetch": want_fetch}
        if dialect == "pg":
            return await _pg_exec(payload)
        if dialect == "mysql":
            return await _my_exec(payload)
        return await _lt_exec(payload)

    if function == "count_table":
        rc = await run(f"select count(*) from ({q}) t", a)
        if rc.get("code") != 200:
            return rc
        cols_out, rows = rc["data"]["cols"], rc["data"]["rows"]
        return _ok({"count": int(rows[0][0]) if rows else 0})
    ob = (args.get("order_by") or "").strip()
    if ob:
        parts = ob.replace(":", " ").split()
        ci_ob = _check_ident({"name": parts[0], "what": "列名"})
        if ci_ob.get("code") != 200:
            return ci_ob                      # 原实现静默忽略 order by，现报错
        if len(parts) > 2 or (len(parts) == 2 and parts[1].lower() not in ("asc", "desc")):
            return _err(f"order_by 仅支持 \"列名\" 或 \"列名:asc|desc\"，收到 {ob!r}",
                        "_sql_dialect_table")
        q += f" order by {qcol(parts[0])}" + (f" {parts[1].upper()}" if len(parts) > 1 else "")
    raw_limit = eff_table_data_limit(args.get("limit"))
    raw_offset = args.get("offset") or 0
    if isinstance(raw_limit, (dict, list, tuple, set)) or isinstance(raw_offset, (dict, list, tuple, set)):
        return _err("limit / offset 必须是整数", "_sql_dialect_table")
    try:
        limit = min(int(raw_limit), eff_max_rows())
        offset = max(int(raw_offset), 0)
    except (TypeError, ValueError):
        return _err("limit / offset 必须是整数", "_sql_dialect_table")
    q += f" limit {limit} offset {offset}"
    rc = await run(q, a)
    if rc.get("code") != 200:
        return rc
    cols_out, rows = rc["data"]["cols"], rc["data"]["rows"]
    rd = _rows_to_dicts({"cols": cols_out, "rows": rows})
    if rd.get("code") != 200:
        return rd
    return _ok({"rows": rd["data"], "returned": len(rows),
                "limit": limit, "offset": offset,
                "note": "需要总行数请用 count_table（同 filters）"})


async def _sql_dialect_query(data: dict = None) -> Dict[str, Any]:
    """只读 SQL 编排（run_query）。

    入参 (data): dialect(必填), cfg(必填), args(可选：sql 必填、database/limit 可选)
    返回: {"code":200, "data":{"columns":[...],"rows":[...],"returned":int}, "message":"success"}
          或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_sql_dialect_query")
    dialect = data.get("dialect")
    if not dialect:
        return _err("缺少 dialect 字段", "_sql_dialect_query")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_sql_dialect_query")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_sql_dialect_query")
    args = data.get("args")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return _err(f"args 必须是字典，收到 {type(args).__name__}", "_sql_dialect_query")
    raw_sql = args.get("sql")
    if raw_sql is not None and not isinstance(raw_sql, (str, bytes, int, float)):
        return _err(f"sql 必须是字符串，收到 {type(raw_sql).__name__}", "_sql_dialect_query")
    sql = (str(raw_sql or "")).strip().rstrip(";")
    if not sql:
        return _err("sql 不能为空", "_sql_dialect_query")
    if ";" in sql:
        return _err("仅允许单条语句", "_sql_dialect_query")
    if not _READONLY_RE.match(sql) or _FORBIDDEN_RE.search(sql):
        return _err("仅允许只读语句（select/with/show/desc/explain），写操作请使用 async_db_write_tools",
                    "_sql_dialect_query")
    db = args.get("database") or cfg.get("database")
    raw_limit = eff_run_query_limit(args.get("limit"))
    if isinstance(raw_limit, (dict, list, tuple, set)):
        return _err("limit 必须是整数", "_sql_dialect_query")
    try:
        limit = min(int(raw_limit), eff_max_rows())
    except (TypeError, ValueError):
        return _err("limit 必须是整数", "_sql_dialect_query")
    q = sql if re.search(r"\blimit\b", sql, re.I) else f"{sql} limit {limit}"
    payload = {"cfg": cfg, "database": db, "sql": q, "fetch": True}
    if dialect == "pg":
        rc = await _pg_exec(payload)
    elif dialect == "mysql":
        rc = await _my_exec(payload)
    else:
        rc = await _lt_exec(payload)
    if rc.get("code") != 200:
        return rc
    cols, rows = rc["data"]["cols"], rc["data"]["rows"]
    rd = _rows_to_dicts({"cols": cols, "rows": rows})
    if rd.get("code") != 200:
        return rd
    return _ok({"columns": cols, "rows": rd["data"], "returned": len(rows)})


async def _sql_dialect_write(data: dict = None) -> Dict[str, Any]:
    """写 SQL 编排（insert_row/update_rows/delete_rows/run_write）。

    入参 (data): dialect(必填), cfg(必填), args(可选), function(必填)
    返回: {"code":200, "data":{"table":...,"affected":int}, "message":"success"}
          或 400 错误信封（含影响行数超上限已回滚）
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_sql_dialect_write")
    dialect = data.get("dialect")
    if not dialect:
        return _err("缺少 dialect 字段", "_sql_dialect_write")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_sql_dialect_write")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_sql_dialect_write")
    args = data.get("args")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return _err(f"args 必须是字典，收到 {type(args).__name__}", "_sql_dialect_write")
    function = data.get("function")
    if not function:
        return _err("缺少 function 字段", "_sql_dialect_write")
    db = args.get("database") or cfg.get("database")
    exec_write = {"pg": _pg_write, "mysql": _my_write, "sqlite": _lt_write}.get(dialect)
    if exec_write is None:
        return _err(f"不支持的方言: {dialect!r}（可写: pg/mysql/sqlite）", "_sql_dialect_write")

    def ph(i):
        r = _wph({"dialect": dialect, "i": i})
        if r.get("code") != 200:
            raise ValueError(str(r.get("message")))     # 由下方统一转 400
        return r["data"]

    def qcol(name):
        r = _qcol({"name": name, "dialect": dialect})
        if r.get("code") != 200:
            raise ValueError(str(r.get("message")))
        return r["data"]

    def qtbl(name):
        r = _qtbl({"name": name, "dialect": dialect})
        if r.get("code") != 200:
            raise ValueError(str(r.get("message")))
        return r["data"]

    try:
        if function == "run_write":
            raw_sql = args.get("sql")
            if raw_sql is not None and not isinstance(raw_sql, (str, bytes, int, float)):
                return _err(f"sql 必须是字符串，收到 {type(raw_sql).__name__}", "_sql_dialect_write")
            sql = (str(raw_sql or "")).strip().rstrip(";")
            if not sql:
                return _err("sql 不能为空", "_sql_dialect_write")
            if ";" in sql:
                return _err("仅允许单条语句", "_sql_dialect_write")
            if not _WRITE_START_RE.match(sql):
                return _err("run_write 仅允许 insert/update/delete 单条语句（查询请用 run_query）",
                            "_sql_dialect_write")
            if _FORBIDDEN_WRITE_RE.search(sql):
                return _err("run_write 含禁用关键词（DDL/授权/过程调用/文件读写等）",
                            "_sql_dialect_write")
            if re.match(r"^\s*(update|delete)\b", sql, re.I) and not re.search(r"\bwhere\b", sql, re.I):
                return _err("update/delete 缺少 where 子句，拒绝全表操作", "_sql_dialect_write")
            rw = await exec_write({"cfg": cfg, "database": db, "sql": sql})
            if rw.get("code") != 200:
                return rw
            return _ok({"affected": rw["data"]["affected"]})

        table = args.get("table")
        ci = _check_ident({"name": table})
        if ci.get("code") != 200:
            return ci
        if function == "insert_row":
            vals = args.get("data") or {}
            if not isinstance(vals, dict) or not vals:
                return _err("data 必须是非空的 {列名: 值} 对象", "_sql_dialect_write")
            for c in vals:
                cc = _check_ident({"name": c, "what": "列名"})
                if cc.get("code") != 200:
                    return cc
            cs = _check_scalars({"vals": vals})
            if cs.get("code") != 200:
                return cs
            cols = list(vals)
            sql = (f"insert into {qtbl(table)} ({', '.join(qcol(c) for c in cols)}) "
                   f"values ({', '.join(ph(i + 1) for i in range(len(cols)))})")
            rw = await exec_write({"cfg": cfg, "database": db, "sql": sql,
                                   "args": [vals[c] for c in cols]})
            if rw.get("code") != 200:
                return rw
            return _ok({"table": table, "affected": rw["data"]["affected"]})

        filters = args.get("filters")
        if not isinstance(filters, dict) or not filters:
            return _err("update/delete 必须携带非空 filters（等值/{like}/{gte}/{lte}，AND 拼接），禁止全表操作",
                        "_sql_dialect_write")
        ww = _write_where({"dialect": dialect, "filters": filters})
        if ww.get("code") != 200:
            return ww
        w, wa = ww["data"]["where"], ww["data"]["args"]
        if function == "update_rows":
            vals = args.get("data") or {}
            if not isinstance(vals, dict) or not vals:
                return _err("data（新值 {列名: 值}）不能为空", "_sql_dialect_write")
            for c in vals:
                cc = _check_ident({"name": c, "what": "列名"})
                if cc.get("code") != 200:
                    return cc
            cs = _check_scalars({"vals": vals})
            if cs.get("code") != 200:
                return cs
            set_ = ", ".join(f"{qcol(c)} = {ph(len(wa) + 1 + i)}" for i, c in enumerate(vals))
            sql = f"update {qtbl(table)} set {set_}{w}"
            rw = await exec_write({"cfg": cfg, "database": db, "sql": sql,
                                   "args": list(vals.values()) + wa})
            if rw.get("code") != 200:
                return rw
            return _ok({"table": table, "affected": rw["data"]["affected"]})

        rw = await exec_write({"cfg": cfg, "database": db,
                               "sql": f"delete from {qtbl(table)}{w}", "args": wa})
        if rw.get("code") != 200:
            return rw
        return _ok({"table": table, "affected": rw["data"]["affected"]})
    except ValueError as e:
        return _err(str(e), "_sql_dialect_write")
