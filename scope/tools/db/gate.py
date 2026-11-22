

"""
库级/表级安全闸门（本工具的核心价值，故独立于辅助层）。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。

规则:
    - allowed_databases / allowed_tables 白名单，denied_databases / denied_tables 黑名单（一票否决）
    - 命中与"不在白名单"回同款文案，不透露对象存在性
    - 系统目录（information_schema/pg_catalog/...）与 SQLite 内部表一律拒绝
    - run_query/run_write 用 sqlglot 提取 SQL 引用的全部表逐一判定，
      **无法完整解析即拒绝（fail-closed）**，且管控下仅允许单条语句
    - 管控字段由平台/管理端注入，模型传参无法覆盖

校验器约定（_tbl_gate / _sql_tbl_check / _db_gate）:
    通过 → {"code":200, ...}；拒绝 → {"code":400, "message": 原因}。
    调用方可直接 `return r` 转发错误信封给上层（原实现是返回错误字符串再由
    调用方拼 _err，多一道转换且易漏前缀）。

注意 _db_same：SQLite 文件模式下"去后缀互认"，白名单与黑名单都应走它。
（原实现 main_db 的 list_databases 输出过滤走精确匹配 x in allow，导致文件夹模式
 启用 allowed_databases 后 list_databases 恒回 []；此处原样保留未改，修时两侧统一。）
"""


import os
import re
from typing import Any, Dict

from ._helper import _db_allowed, _err, _ok, _target_db


_TBL_CATALOGS = ("information_schema", "pg_catalog", "mysql", "performance_schema", "sys")
_SCHEMAISH = ("main", "temp", "public", "dbo")

_SQLGLOT_DIALECT = {"postgresql": "postgres", "pg": "postgres",
                    "mysql": "mysql", "sqlite": "sqlite"}


def _tbl_list(data: dict = None) -> Dict[str, Any]:
    """db_config 表级管控字段 → 小写清洗后的条目列表（空=不限制）。

    入参 (data): cfg(dict, 必填), key(str, 必填) 管控字段名
    返回: {"code":200, "data": [str, ...], "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_tbl_list")
    cfg, key = data.get("cfg"), data.get("key")
    if cfg is None:
        return _err("缺少 cfg 字段", "_tbl_list")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_tbl_list")
    if not key:
        return _err("缺少 key 字段（管控字段名）", "_tbl_list")
    v = cfg.get(key)
    if isinstance(v, str):
        v = [s for s in re.split(r"[,;|\s]+", v) if s.strip()]
    if not isinstance(v, (list, tuple)):
        return _ok([])
    return _ok([str(x).strip().lower() for x in v if str(x).strip()])


def _stem(data: dict = None) -> Dict[str, Any]:
    """去扩展名的末段名（SQLite 文件名互认用）。

    入参 (data): s(any, 可选)
    返回: {"code":200, "data": str, "message":"success"} 或 400 错误信封
    """
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_stem")
    s = data.get("s")
    if isinstance(s, (dict, list, tuple, set)):
        return _err(f"s 必须是字符串，收到 {type(s).__name__}", "_stem")
    return _ok(os.path.splitext(str(s or "").strip())[0])


def _db_same(data: dict = None) -> Dict[str, Any]:
    """同库/同文件判定（不分大小写；sqlite 文件模式去后缀互认）。

    入参 (data): a(any, 可选), b(any, 可选)
    返回: {"code":200, "data": bool, "message":"success"} 或 400 错误信封
    """
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_db_same")
    for k in ("a", "b"):
        v = data.get(k)
        if isinstance(v, (dict, list, tuple, set)):
            return _err(f"{k} 必须是字符串，收到 {type(v).__name__}", "_db_same")
    a, b = str(data.get("a") or "").strip().lower(), str(data.get("b") or "").strip().lower()
    if not (a and b):
        return _ok(False)
    if a == b:
        return _ok(True)
    sa, sb = _stem({"s": a}), _stem({"s": b})
    if sa.get("code") != 200 or sb.get("code") != 200:
        return sa if sa.get("code") != 200 else sb
    return _ok(sa["data"] == sb["data"])


def _tbl_hit(data: dict = None) -> Dict[str, Any]:
    """管控条目（已小写）× (库, 表) 命中判定。

    入参 (data):
        entry(str, 必填)   管控条目；"库.表" 按首个点拆分，裸条目=全库同名表
        db(str, 可选)      目标库；缺失时限定条目不匹配（fail-closed）
        table(str, 可选)   表名；表部分对 schema.table 取末段互认

    返回: {"code":200, "data": bool, "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_tbl_hit")
    entry = data.get("entry")
    if not entry:
        return _err("缺少 entry 字段（管控条目）", "_tbl_hit")
    for k in ("db", "table"):
        v = data.get(k)
        if isinstance(v, (dict, list, tuple, set)):
            return _err(f"{k} 必须是字符串，收到 {type(v).__name__}", "_tbl_hit")
    db_s = str(data.get("db") or "").strip().lower()
    tbl = str(data.get("table") or "").strip().lower()
    if not tbl:
        return _ok(False)
    e = str(entry).strip().lower()
    if "." in e:
        edb, etbl = e.split(".", 1)
        ds = _db_same({"a": edb, "b": db_s})
        if ds.get("code") != 200:
            return ds
        if not ds["data"]:
            return _ok(False)
    else:
        etbl = e
    return _ok(etbl in (tbl, tbl.split(".")[-1]))


def _tbl_denied_msg(data: dict = None) -> Dict[str, Any]:
    """拒绝文案（黑名单命中与白名单未命中同款，不透露对象存在性）。

    入参 (data): what(str, 可选), table(str, 必填)
    返回: {"code":200, "data": str, "message":"success"} 或 400 错误信封
    """
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_tbl_denied_msg")
    table = data.get("table")
    if table is None:
        return _err("缺少 table 字段", "_tbl_denied_msg")
    if isinstance(table, (dict, list, tuple, set)):
        return _err(f"table 必须是字符串，收到 {type(table).__name__}", "_tbl_denied_msg")
    what = str(data.get("what") or "表")
    return _ok(f"{what} '{table}' 不在可访问范围内")


def _tbl_gate(data: dict = None) -> Dict[str, Any]:
    """表级强制点（超管黑名单 + 用户可读表白名单）。**校验器**：200 通过 / 400 拒绝。

    入参 (data):
        cfg(dict, 必填)       连接配置（含管控字段）
        db(str, 可选)         目标库
        table(str, 可选)      表名（管控生效时必填）
        what(str, 可选)       拒绝文案里的对象名，默认 "表"

    返回:
        {"code":200, "data":{"allowed": True}, "message":"success"}          放行
        {"code":400, "data": 位置, "message": "错误：<原因>"}                 拒绝

    allowed_tables 空=不限制（仍受黑名单约束）；黑名单命中与白名单未命中返回同款文案，
    模型无法区分"表不存在"与"被禁止"；管控生效时系统目录（information_schema/pg_catalog
    /mysql 库/pg_*/sqlite_* 表）一律拒绝，防借目录泄露被隐藏对象名。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_tbl_gate")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_tbl_gate")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_tbl_gate")
    for k in ("db", "table", "what"):
        v = data.get(k)
        if v is not None and isinstance(v, (dict, list, tuple, set)):
            return _err(f"{k} 必须是字符串，收到 {type(v).__name__}", "_tbl_gate")

    def _lst(key):
        r = _tbl_list({"cfg": cfg, "key": key})
        if r.get("code") != 200:
            return None, r
        return r["data"], None

    deny_dbs, e = _lst("denied_databases")
    if e:
        return e
    deny_tbls, e = _lst("denied_tables")
    if e:
        return e
    allow_tbls, e = _lst("allowed_tables")
    if e:
        return e
    db_s = str(data.get("db") or "").strip()
    for entry in deny_dbs:
        ds = _db_same({"a": entry, "b": db_s})
        if ds.get("code") != 200:
            return ds
        if ds["data"]:
            return _err(f"数据库 '{db_s}' 不在可访问范围内", "_tbl_gate")
    if not (deny_tbls or allow_tbls or deny_dbs):
        return _ok({"allowed": True})
    table = data.get("table")
    if not table:
        return _err("已启用表级管控，必须提供表名（table 需指向可访问对象）", "_tbl_gate")
    what = str(data.get("what") or "表")
    t_s = str(table).strip()
    t_low = t_s.lower()
    segs = t_low.split(".")
    if segs[0] in _TBL_CATALOGS or db_s.lower() in _TBL_CATALOGS:
        return _err(_tbl_denied_msg({"what": what, "table": t_s})["data"], "_tbl_gate")
    if segs[-1].startswith("pg_") or segs[-1].startswith("sqlite_"):
        return _err(_tbl_denied_msg({"what": what, "table": t_s})["data"], "_tbl_gate")

    def _hits(entries):
        for entry in entries:
            h = _tbl_hit({"entry": entry, "db": db_s, "table": t_s})
            if h.get("code") != 200:
                return None, h
            if h["data"]:
                return True, None
        return False, None

    hit_deny, e = _hits(deny_tbls)
    if e:
        return e
    if hit_deny:
        return _err(_tbl_denied_msg({"what": what, "table": t_s})["data"], "_tbl_gate")
    if allow_tbls:
        hit_allow, e = _hits(allow_tbls)
        if e:
            return e
        if not hit_allow:
            base = _tbl_denied_msg({"what": what, "table": t_s})["data"]
            return _err(f"{base}（可读表白名单: {allow_tbls[:30]}）", "_tbl_gate")
    return _ok({"allowed": True})


def _sql_table_refs(data: dict = None) -> Dict[str, Any]:
    """sqlglot 提取 SQL 引用的表（CTE 名不算引用）。

    入参 (data): sql(str, 必填), dialect(str, 必填)

    返回:
        {"code":200, "data": [{"catalog":str,"db":str,"name":str}, ...], "message":"success"}
            均小写；空语句/无引用时 data 为空列表
        {"code":400, ...}  无 sqlglot / 方言不支持 / 解析失败 —— 调用方须 fail-closed

    调用方判 code 而非 None，与原语义（返回 None 表示"无法解析"）一致。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_sql_table_refs")
    sql = data.get("sql")
    if sql is None:
        return _err("缺少 sql 字段", "_sql_table_refs")
    if isinstance(sql, (dict, list, tuple, set)):
        return _err(f"sql 必须是字符串，收到 {type(sql).__name__}", "_sql_table_refs")
    dialect = data.get("dialect")
    if isinstance(dialect, (dict, list, tuple, set)):
        return _err(f"dialect 必须是字符串，收到 {type(dialect).__name__}", "_sql_table_refs")
    try:
        import sqlglot
        from sqlglot import expressions as exp
    except ImportError:
        return _err("未安装 sqlglot，无法解析 SQL 引用的表", "_sql_table_refs")
    d = _SQLGLOT_DIALECT.get(str(dialect or "").lower())
    if d is None:
        return _err(f"不支持的方言: {dialect!r}（可解析: {sorted(_SQLGLOT_DIALECT)}）",
                    "_sql_table_refs")
    try:
        trees = [t for t in sqlglot.parse(str(sql), read=d) if t is not None]
        if not trees:
            return _err("SQL 解析结果为空", "_sql_table_refs")
        out = []
        for t in trees:
            ctes = {str(c.alias_or_name).strip().lower()
                    for c in t.find_all(exp.CTE) if c.alias_or_name}
            for tb in t.find_all(exp.Table):
                name = str(tb.name or "").strip().lower()
                if not name:
                    continue
                db_part = str(tb.db or "").strip().lower()
                cat_part = str(tb.catalog or "").strip().lower()
                if not db_part and not cat_part and name in ctes:
                    continue
                out.append({"catalog": cat_part, "db": db_part, "name": name})
        return _ok(out)
    except Exception as e:
        return _err(f"SQL 解析失败：{type(e).__name__}: {e}", "_sql_table_refs")


def _sql_tbl_check(data: dict = None) -> Dict[str, Any]:
    """run_query/run_write 的 SQL 表级校验（仅管控生效时调用）。**校验器**：200 通过 / 400 拒绝。

    入参 (data):
        cfg(dict, 必填)         连接配置（含管控字段）
        target_db(str, 可选)    目标库
        dialect(str, 必填)      方言
        sql(str, 必填)          待执行的 SQL
        write(bool, 可选)       写上下文（限 insert/update/delete）

    返回: {"code":200, "data":{"allowed": True, "refs": [...]}, "message":"success"}
          或 {"code":400, "data": 位置, "message": "错误：<原因>"}

    每个表引用按合理解释（目标库内 schema 限定 / 跨库引用 / 裸表名）任一通过即放行；
    黑名单命中在任何解释下都会被末段名匹配兜住，不存在绕过解释。
    无法完整解析即拒绝（fail-closed）；管控下查询仅允许单条 select/with、写仅 insert/update/delete。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_sql_tbl_check")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_sql_tbl_check")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_sql_tbl_check")
    sql = data.get("sql")
    if sql is None:
        return _err("缺少 sql 字段", "_sql_tbl_check")
    if isinstance(sql, (dict, list, tuple, set)):
        return _err(f"sql 必须是字符串，收到 {type(sql).__name__}", "_sql_tbl_check")
    write = bool(data.get("write", False))
    if write:
        if not re.match(r"^\s*(insert|update|delete)\b", str(sql or "").strip(), re.I):
            return _err("表级管控已启用，run_write 仅支持单条 insert/update/delete 语句",
                        "_sql_tbl_check")
    elif not re.match(r"^\s*(select|with)\b", str(sql or "").strip(), re.I):
        return _err("表级管控已启用，run_query 仅支持单条 select/with 语句"
                    "（列表/看结构请改用 list_tables/describe_table）", "_sql_tbl_check")
    refs_r = _sql_table_refs({"sql": sql, "dialect": data.get("dialect")})
    if refs_r.get("code") != 200:
        return _err("表级管控已启用，无法完整解析 SQL 引用的表，拒绝执行"
                    "（可改用结构化查询函数 table_data/describe_table/count_table）",
                    "_sql_tbl_check")
    refs = refs_r["data"]
    target_db = str(data.get("target_db") or "").strip()
    for r in refs:
        parts = [x for x in (r["catalog"], r["db"]) if x]
        cands = []
        if not parts:
            cands.append((target_db, r["name"]))
        elif len(parts) == 1:
            q = parts[0]
            ds = _db_same({"a": q, "b": target_db})
            if ds.get("code") != 200:
                return ds
            if ds["data"] or q in _SCHEMAISH:
                cands.append((target_db, r["name"]))
            cands.append((target_db, f"{q}.{r['name']}"))
            if q not in _SCHEMAISH:
                cands.append((q, r["name"]))
        else:
            cat, sch = parts
            tbl_s = r["name"] if sch in _SCHEMAISH else f"{sch}.{r['name']}"
            dc = _db_same({"a": cat, "b": target_db})
            if dc.get("code") != 200:
                return dc
            if dc["data"]:
                cands.append((target_db, tbl_s))
                cands.append((target_db, r["name"]))
            cands.append((cat, tbl_s))
            cands.append((cat, r["name"]))
        # 所有候选都被拒（code != 200）才判定该引用不可访问
        all_denied = True
        last_err = None
        for (d, t) in cands:
            g = _tbl_gate({"cfg": cfg, "db": d, "table": t})
            if g.get("code") == 200:
                all_denied = False
                break
            last_err = g
        if all_denied:
            full = ".".join([x for x in (r["catalog"], r["db"], r["name"]) if x])
            if last_err is not None and str(last_err.get("message", "")).startswith("错误："):
                return last_err
            g2 = _tbl_gate({"cfg": cfg, "db": target_db, "table": full or r["name"]})
            if g2.get("code") != 200:
                return g2
            return _err(_tbl_denied_msg({"what": "表", "table": full})["data"], "_sql_tbl_check")
    return _ok({"allowed": True, "refs": refs})


def _db_gate(data: dict = None) -> Dict[str, Any]:
    """白名单/黑名单/写权限强制点。**校验器**：200 通过 / 400 拒绝。

    入参 (data):
        cfg(dict, 必填)      连接配置（含管控字段）
        args(dict, 可选)     本次操作的业务参数（database/table/sql）
        write(bool, 可选)    写上下文

    返回:
        {"code":200, "data":{"allowed": True, "target_db": str}, "message":"success"}
        或 {"code":400, "data": 位置, "message": "错误：<原因>"}

    库维度：allowed_databases 非空时除 list_databases 外必须指定名单内库；
    denied_databases 超管一票否决（无需白名单也生效）。
    表维度：table 参数直接判定；sql 参数提取全部引用表判定（fail-closed）；
    allowed_tables 空=不限但黑名单始终生效。
    allow_write=false 时写工具整体禁用。

    target_db 随 200 一起返回，调用方不必再单独调 _target_db
    （白名单去后缀互认时它可能被改写为名单内的写法）。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_db_gate")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_db_gate")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_db_gate")
    args = data.get("args")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return _err(f"args 必须是字典，收到 {type(args).__name__}", "_db_gate")
    write = bool(data.get("write", False))
    if write and cfg.get("allow_write") is False:
        return _err("写操作（增删改）已被管理端设置禁用（allow_write=false），请仅使用只读查询工具",
                    "_db_gate")
    td = _target_db({"cfg": cfg, "args": args})
    if td.get("code") != 200:
        return td
    target = td["data"]
    dl = _tbl_list({"cfg": cfg, "key": "denied_databases"})
    if dl.get("code") != 200:
        return dl
    for entry in dl["data"]:
        ds = _db_same({"a": entry, "b": target})
        if ds.get("code") != 200:
            return ds
        if ds["data"]:
            return _err(f"数据库 '{target}' 不在可访问范围内", "_db_gate")
    al = _db_allowed({"cfg": cfg})
    if al.get("code") != 200:
        return al
    allow = al["data"]
    if allow:
        if not target:
            return _err(f"已启用数据库白名单，必须指定 database 参数（可操作库: {allow}）",
                        "_db_gate")
        if target not in allow:
            if str(cfg.get("db_type") or "").lower() == "sqlite":
                st = _stem({"s": target})
                if st.get("code") != 200:
                    return st
                stem = st["data"]
                matched = None
                for a in allow:
                    sa = _stem({"s": a})
                    if sa.get("code") != 200:
                        return sa
                    if sa["data"] == stem:
                        matched = a
                        break
                if matched is None:
                    return _err(f"数据库 '{target}' 不在可操作白名单内（可操作库: {allow}）",
                                "_db_gate")
                target = matched
            else:
                return _err(f"数据库 '{target}' 不在可操作白名单内（可操作库: {allow}）",
                            "_db_gate")
    if args.get("table"):
        g = _tbl_gate({"cfg": cfg, "db": target, "table": args.get("table")})
        if g.get("code") != 200:
            return g
        return _ok({"allowed": True, "target_db": target})
    dt = _tbl_list({"cfg": cfg, "key": "denied_tables"})
    at = _tbl_list({"cfg": cfg, "key": "allowed_tables"})
    if dt.get("code") != 200:
        return dt
    if at.get("code") != 200:
        return at
    if args.get("sql") and (dt["data"] or at["data"]):
        c = _sql_tbl_check({"cfg": cfg, "target_db": target,
                            "dialect": str(cfg.get("db_type") or "").lower(),
                            "sql": args["sql"], "write": write})
        if c.get("code") != 200:
            return c
        return _ok({"allowed": True, "target_db": target})
    return _ok({"allowed": True, "target_db": target})


def _tbl_filter_out(data: dict = None) -> Dict[str, Any]:
    """list_tables 结果按表级管控过滤。

    入参 (data):
        cfg(dict, 必填)       连接配置
        target(str, 可选)     目标库
        out(list, 必填)       [{"schema","table"}...] 或 ["名"...] 两种形态

    返回: {"code":200, "data": 过滤后的列表, "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_tbl_filter_out")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_tbl_filter_out")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_tbl_filter_out")
    out = data.get("out")
    if out is None:
        return _err("缺少 out 字段（待过滤的表清单）", "_tbl_filter_out")
    target = data.get("target")
    if isinstance(target, (dict, list, tuple, set)):
        return _err(f"target 必须是字符串，收到 {type(target).__name__}", "_tbl_filter_out")
    target = str(target or "").strip()
    dt = _tbl_list({"cfg": cfg, "key": "denied_tables"})
    at = _tbl_list({"cfg": cfg, "key": "allowed_tables"})
    if dt.get("code") != 200:
        return dt
    if at.get("code") != 200:
        return at
    if not (dt["data"] or at["data"]):
        return _ok(out)

    def keep(name):
        name = str(name or "").strip()
        if not name:
            return False, None
        g = _tbl_gate({"cfg": cfg, "db": target, "table": name})
        if g.get("code") != 200:
            return False, g
        return True, None

    if not isinstance(out, list):
        return _err(f"out 必须是列表，收到 {type(out).__name__}", "_tbl_filter_out")
    res = []
    for r in out:
        if out and isinstance(out[0], dict) and isinstance(r, dict):
            ok_flag, e = keep(r.get("table"))
        else:
            ok_flag, e = keep(r)
        if e:
            return e
        if ok_flag:
            res.append(r)
    return _ok(res)
