

"""
db 工具的无状态辅助层。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封；
参数错误一律 if 判断后返回 code 400，不裸抛。

三组内容:
  1. 常量、上限、正则与统一返回信封 _err/_ok
     —— 上限均为服务端硬钳制：查询行数 _MAX_ROWS、写入影响行数 _MAX_AFFECT；
        _err/_ok 是全模块共用的返回形状，改这里即改全局契约
  2. 连接配置归一化与 SQLite 目标路径解析
     —— _resolve 决定 db_type 与连接字段（字符串字段清洗首尾空白）；
        SQLite 支持单文件（path）与文件夹（dir）两种模式，写操作不自动建库
  3. 标识符校验、列/表引用、参数化占位符、值翻译、Mongo 过滤器构造
     —— 全部无副作用；值一律参数化传递以防注入

本模块不建连接、不碰数据库驱动；执行在 executors.py，编排在 dialect.py，
安全判定在 gate.py。

校验器约定（_check_ident / _check_scalars）:
    通过 → {"code":200, ...}；不通过 → {"code":400, "message": 原因}。
    调用方可直接 `return r` 把错误信封转发给上层，无需再拼字符串。
"""


import os
import re
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Dict


_DEFAULT_PORTS = {"postgresql": 5432, "mysql": 3306, "mongodb": 27017}
_SQLITE_EXTS = (".db", ".sqlite", ".sqlite3")
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*(\.[A-Za-z_][A-Za-z0-9_$]*)?$")
_READONLY_RE = re.compile(r"^\s*(select|with|show|desc|describe|explain)\b", re.I)
_FORBIDDEN_RE = re.compile(r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|copy|merge|call|execute|set|do|vacuum|attach|detach|pragma)\b", re.I)
_MAX_ROWS = 500

_WRITE_START_RE = re.compile(r"^\s*(insert|update|delete)\b", re.I)
_FORBIDDEN_WRITE_RE = re.compile(
    r"\b(drop|alter|truncate|create|grant|revoke|copy|merge|call|execute|exec|do|vacuum|"
    r"shutdown|kill|lock|unlock|outfile|dumpfile|load_file|sleep|benchmark|load\s+data|"
    r"attach|detach|pragma|reindex)\b", re.I)
_MAX_AFFECT = 100


def _err(msg: str, where: str = "async_db_tools") -> Dict[str, Any]:
    """错误信封。where 指向**实际出错**的函数名（原实现硬编码 async_db_tools，
    导致所有闸门/配置错误都报同一位置、无诊断价值；现由各调用方传入）。"""
    return {"code": 400, "data": f"{os.path.abspath(__file__)}_{where}", "message": f"错误：{msg}"}


def _ok(data=None, message: str = "success") -> Dict[str, Any]:
    return {"code": 200, "data": data, "message": message}


def _resolve(data: dict = None) -> Dict[str, Any]:
    """归一化连接配置。

    入参 (data):
        db_config(dict, 可选)  连接配置段；其字段也可平铺在 data 顶层（db_config 优先）

    返回:
        {"code":200, "data":{"db_type": str, "cfg": dict}, "message":"success"}
        或 {"code":400, "data": 位置, "message": 错误描述}

    字符串字段清洗首尾空白；db_type 别名归一（postgres/pg→postgresql，mongo→mongodb，
    sqlite3→sqlite）。
    """
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_resolve")
    raw_cfg = data.get("db_config")
    if raw_cfg is None:
        raw_cfg = {}
    if not isinstance(raw_cfg, dict):
        return _err(f"db_config 必须是字典，收到 {type(raw_cfg).__name__}", "_resolve")
    cfg = dict(raw_cfg)
    for k in ("db_type", "host", "port", "user", "password", "database", "path", "dir"):
        if k in data and data[k] not in (None, ""):
            cfg.setdefault(k, data[k])
    for k in ("db_type", "host", "user", "password", "database", "port", "path", "dir"):
        if isinstance(cfg.get(k), str):
            cfg[k] = cfg[k].strip()
    db_type = str(cfg.get("db_type") or "postgresql").lower().strip()
    if db_type in ("postgres", "postgresql", "pg"):
        db_type = "postgresql"
    elif db_type in ("mysql", "mongodb", "mongo"):
        db_type = "mysql" if db_type == "mysql" else "mongodb"
    elif db_type in ("sqlite", "sqlite3"):
        db_type = "sqlite"
    else:
        return _err(f"不支持的数据库类型: {db_type}（postgresql/mysql/mongodb/sqlite）", "_resolve")
    if db_type == "sqlite":
        if not (cfg.get("path") or cfg.get("dir")):
            return _err("SQLite 需配置 db_config.path（单数据库文件）或 db_config.dir（存放多个 sqlite 文件的文件夹）", "_resolve")
        return _ok({"db_type": db_type, "cfg": cfg})
    if not cfg.get("host"):
        return _err("缺少数据库连接配置（db_config.host）", "_resolve")
    cfg.setdefault("port", _DEFAULT_PORTS[db_type])
    return _ok({"db_type": db_type, "cfg": cfg})


def _sqlite_target_path(data: dict = None) -> Dict[str, Any]:
    """解析 SQLite 目标文件绝对路径。

    入参 (data):
        cfg(dict, 必填)         已归一化的连接配置
        database(str, 可选)     目标库名（文件夹模式=纯文件名，可省后缀）
        for_write(bool, 可选)   写操作上下文（语义同前：不自动建库）

    返回:
        {"code":200, "data":{"path": str}, "message":"success"}
        或 {"code":400, "data": 位置, "message": 错误描述}

    path=单文件模式（database 只允许指向该文件）；dir=文件夹模式（database=纯文件名，
    可省后缀，扩展名限 _SQLITE_EXTS，拒路径分隔符与 ..）。文件必须已存在——
    for_write 同样（写操作不自动建库，防 AI 随手生成垃圾 db）。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_sqlite_target_path")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段（已归一化的连接配置）", "_sqlite_target_path")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_sqlite_target_path")
    raw_path = str(cfg.get("path") or "").strip()
    raw_dir = str(cfg.get("dir") or "").strip()
    if raw_path and raw_dir:
        return _err("db_config sqlite 模式冲突：path（单文件）与 dir（文件夹）只能二选一",
                    "_sqlite_target_path")
    db = str(data.get("database") or "").strip()
    if raw_path:
        p = os.path.abspath(os.path.expanduser(raw_path))
        if not os.path.isfile(p):
            return _err(f"SQLite 文件不存在: {p}", "_sqlite_target_path")
        fname = os.path.basename(p)
        if db and db not in (fname, os.path.splitext(fname)[0]):
            return _err(f"单文件模式固定为 {fname}，不能指定 database={db!r}",
                        "_sqlite_target_path")
        return _ok({"path": p})
    if raw_dir:
        d = os.path.abspath(os.path.expanduser(raw_dir))
        if not os.path.isdir(d):
            return _err(f"SQLite 文件夹不存在: {d}", "_sqlite_target_path")
        if not db:
            return _err("文件夹模式必须指定 database（文件夹内的 sqlite 文件名）",
                        "_sqlite_target_path")
        base = os.path.basename(db.replace("\\", "/").strip("/"))
        if base != db or base in ("", ".", ".."):
            return _err(f"非法 database 文件名: {db!r}（文件夹模式只接受纯文件名，不允许路径）",
                        "_sqlite_target_path")
        stem = os.path.splitext(base)[0]
        cands = [base] + [stem + e for e in _SQLITE_EXTS if stem + e != base]
        for c in cands:
            p = os.path.abspath(os.path.join(d, c))
            if not p.startswith(d + os.sep):
                continue
            if os.path.isfile(p):
                if os.path.splitext(p)[1].lower() not in _SQLITE_EXTS:
                    return _err("文件名扩展名必须是 .db/.sqlite/.sqlite3 之一",
                                "_sqlite_target_path")
                return _ok({"path": p})
        try:
            avail = sorted(f for f in os.listdir(d)
                           if f.lower().endswith(_SQLITE_EXTS) and os.path.isfile(os.path.join(d, f)))
        except OSError:
            avail = []
        return _err(f"文件夹内未找到 SQLite 文件 '{base}'（可用: {avail[:20]}）",
                    "_sqlite_target_path")
    return _err("SQLite 需配置 db_config.path（单数据库文件）或 db_config.dir（sqlite 文件文件夹）",
                "_sqlite_target_path")


def _sqlite_databases(data: dict = None) -> Dict[str, Any]:
    """list_databases 语义：单文件模式=[文件名]；文件夹模式=目录内 sqlite 文件名列表。

    入参 (data): cfg(dict, 必填) 已归一化的连接配置
    返回: {"code":200, "data": [str, ...], "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_sqlite_databases")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_sqlite_databases")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_sqlite_databases")
    raw_path = str(cfg.get("path") or "").strip()
    if raw_path:
        return _ok([os.path.basename(os.path.abspath(os.path.expanduser(raw_path)))])
    d = os.path.abspath(os.path.expanduser(str(cfg.get("dir") or ".")))
    try:
        return _ok(sorted(f for f in os.listdir(d)
                          if f.lower().endswith(_SQLITE_EXTS) and os.path.isfile(os.path.join(d, f))))
    except OSError:
        return _ok([])


def _db_allowed(data: dict = None) -> Dict[str, Any]:
    """db_config.allowed_databases → 清洗后的库名列表（空=不限制）。

    入参 (data): cfg(dict, 必填)
    返回: {"code":200, "data": [str, ...], "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_db_allowed")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_db_allowed")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_db_allowed")
    allow = cfg.get("allowed_databases")
    if isinstance(allow, str):
        allow = [s for s in re.split(r"[,;|\s]+", allow) if s.strip()]
    if not isinstance(allow, (list, tuple)):
        return _ok([])
    return _ok([str(x).strip() for x in allow if str(x).strip()])


def _target_db(data: dict = None) -> Dict[str, Any]:
    """解析本次操作的目标库：args.database > cfg.database；
    sqlite 单文件模式缺省回落到库文件名（与 _db_gate 原语义一致）。

    入参 (data): cfg(dict, 必填), args(dict, 可选)
    返回: {"code":200, "data": str, "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_target_db")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_target_db")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_target_db")
    args = data.get("args")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return _err(f"args 必须是字典，收到 {type(args).__name__}", "_target_db")
    target = str(args.get("database") or cfg.get("database") or "").strip()
    if (not target and str(cfg.get("db_type") or "").lower() == "sqlite"
            and str(cfg.get("path") or "").strip()):
        target = os.path.basename(os.path.abspath(os.path.expanduser(str(cfg["path"]))))
    return _ok(target)


def _check_ident(data: dict = None) -> Dict[str, Any]:
    """标识符校验（表名/列名）。**校验器**：通过返回 200，不通过返回 400。

    入参 (data):
        name(str, 必填)   待校验标识符
        what(str, 可选)   出错文案里的对象名，默认 "表名"

    返回:
        {"code":200, "data":{"name": str}, "message":"success"}   通过
        {"code":400, "data": 位置, "message": "错误：非法表名: ..."}  不通过

    仅允许字母/数字/_/$，最多 schema.table。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_check_ident")
    name = data.get("name")
    what = str(data.get("what") or "表名")
    if name is not None and isinstance(name, (dict, list, tuple, set)):
        return _err(f"{what} 必须是字符串，收到 {type(name).__name__}", "_check_ident")
    if not name or not _IDENT_RE.match(str(name).strip()):
        return _err(f"非法{what}: {name!r}（仅允许字母/数字/_/$，最多 schema.table）",
                    "_check_ident")
    return _ok({"name": str(name).strip()})


def _jsonable(data: dict = None) -> Dict[str, Any]:
    """把数据库原生类型转成 JSON 可表达的值（datetime→isoformat，Decimal→int/float，
    bytes→前 256 字节 hex），其余原样返回。

    入参 (data): v(any, 必填) 待转换值
    返回: {"code":200, "data": 转换后的值, "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_jsonable")
    if "v" not in data:
        return _err("缺少 v 字段（待转换值）", "_jsonable")
    v = data["v"]
    if isinstance(v, (datetime, date, time)):
        return _ok(v.isoformat())
    if isinstance(v, Decimal):
        return _ok(float(v) if "." in str(v) else int(v))
    if isinstance(v, (bytes, bytearray)):
        return _ok(v[:256].hex())
    return _ok(v)


def _rows_to_dicts(data: dict = None) -> Dict[str, Any]:
    """(列名, 行元组列表) → 字典行列表，逐值过 _jsonable。

    入参 (data): cols(list, 必填), rows(list, 必填)
    返回: {"code":200, "data": [dict, ...], "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_rows_to_dicts")
    cols, rows = data.get("cols"), data.get("rows")
    if cols is None:
        return _err("缺少 cols 字段（列名序列）", "_rows_to_dicts")
    if rows is None:
        return _err("缺少 rows 字段（行序列）", "_rows_to_dicts")
    if not isinstance(cols, (list, tuple)):
        return _err(f"cols 必须是列表，收到 {type(cols).__name__}", "_rows_to_dicts")
    if not isinstance(rows, (list, tuple)):
        return _err(f"rows 必须是列表，收到 {type(rows).__name__}", "_rows_to_dicts")
    out = []
    for r in rows:
        row = {}
        for i, c in enumerate(cols):
            jr = _jsonable({"v": r[i] if i < len(r) else None})
            if jr.get("code") != 200:
                return jr
            row[c] = jr["data"]
        out.append(row)
    return _ok(out)


def _mongo_filters(data: dict = None) -> Dict[str, Any]:
    """业务 filters → Mongo 查询条件（{"like":"%x%"} → {"$regex":"x.*"}）。

    入参 (data): spec(dict, 可选) 业务筛选条件
    返回: {"code":200, "data": dict, "message":"success"} 或 400 错误信封
    """
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_mongo_filters")
    spec = data.get("spec")
    if spec is None:
        spec = {}
    if not isinstance(spec, dict):
        return _err(f"spec 必须是字典，收到 {type(spec).__name__}", "_mongo_filters")
    out = {}
    for k, v in spec.items():
        if isinstance(v, dict) and "like" in v:
            out[k] = {"$regex": str(v["like"]).replace("%", ".*")}
        else:
            out[k] = v
    return _ok(out)


# ---------- 写操作（async_db_write_tools）的 SQL 构造 ----------

def _qcol(data: dict = None) -> Dict[str, Any]:
    """列名加方言引号：mysql → 反引号，其余 → 双引号。

    入参 (data): name(str, 必填), dialect(str, 必填, pg/mysql/sqlite)
    返回: {"code":200, "data": str, "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_qcol")
    name, dialect = data.get("name"), data.get("dialect")
    if name is None:
        return _err("缺少 name 字段（列名）", "_qcol")
    if isinstance(name, (dict, list, tuple, set)):
        return _err(f"name 必须是字符串，收到 {type(name).__name__}", "_qcol")
    if not dialect:
        return _err("缺少 dialect 字段（方言 pg/mysql/sqlite）", "_qcol")
    return _ok(f"`{name}`" if dialect == "mysql" else f'"{name}"')


def _qtbl(data: dict = None) -> Dict[str, Any]:
    """表名（可含 schema.）逐段加引号后用点连接。

    入参 (data): name(str, 必填), dialect(str, 必填)
    返回: {"code":200, "data": str, "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_qtbl")
    name, dialect = data.get("name"), data.get("dialect")
    if name is None:
        return _err("缺少 name 字段（表名）", "_qtbl")
    if isinstance(name, (dict, list, tuple, set)):
        return _err(f"name 必须是字符串，收到 {type(name).__name__}", "_qtbl")
    if not dialect:
        return _err("缺少 dialect 字段", "_qtbl")
    parts = []
    for p in str(name).split("."):
        rq = _qcol({"name": p, "dialect": dialect})
        if rq.get("code") != 200:
            return rq
        parts.append(rq["data"])
    return _ok(".".join(parts))


def _wph(data: dict = None) -> Dict[str, Any]:
    """占位符按方言：pg → $i，mysql → %s，sqlite → ?。

    入参 (data): dialect(str, 必填), i(int, 可选, pg 的序号，默认 1)
    返回: {"code":200, "data": str, "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_wph")
    dialect = data.get("dialect")
    if not dialect:
        return _err("缺少 dialect 字段", "_wph")
    raw_i = data.get("i", 1)
    if isinstance(raw_i, (dict, list, tuple, set)):
        return _err(f"i 必须是整数，收到 {type(raw_i).__name__}", "_wph")
    try:
        i = int(raw_i if raw_i not in (None, "") else 1)
    except (TypeError, ValueError):
        return _err("i 必须是整数", "_wph")
    return _ok(f"${i}" if dialect == "pg" else ("%s" if dialect == "mysql" else "?"))


def _write_where(data: dict = None) -> Dict[str, Any]:
    """filters → WHERE 子句（等值/like/gte/lte，AND 拼接）；值全部参数化以防注入。
    严格模式：非法列名/未知操作符直接返回 400。

    入参 (data):
        dialect(str, 必填)          pg / mysql / sqlite
        filters(dict, 可选)         {"列": 值} 或 {"列": {"like"|"gte"|"lte": 值}}

    返回:
        {"code":200, "data":{"where": str, "args": [值...]}, "message":"success"}
        （where 形如 " where `a` = %s and `b` >= %s"，无命中时为空串）
        或 {"code":400, "data": 位置, "message": 错误描述}
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_write_where")
    dialect = data.get("dialect")
    if not dialect:
        return _err("缺少 dialect 字段", "_write_where")
    filters = data.get("filters")
    if filters is None:
        filters = {}
    if not isinstance(filters, dict):
        return _err(f"filters 必须是字典，收到 {type(filters).__name__}", "_write_where")
    where, a, idx = [], [], 1
    for col, val in filters.items():
        ci = _check_ident({"name": col, "what": "列名"})
        if ci.get("code") != 200:
            return ci
        if isinstance(val, dict):
            unknown = set(val) - {"like", "gte", "lte"}
            if unknown:
                return _err(f"不支持的筛选操作符: {sorted(unknown)}（仅等值/like/gte/lte）",
                            "_write_where")
            if "like" in val:
                op, v = "like", val["like"]
            elif "gte" in val:
                op, v = ">=", val["gte"]
            elif "lte" in val:
                op, v = "<=", val["lte"]
            else:
                return _err(f"列 {col} 的条件对象为空，请用等值或 like/gte/lte", "_write_where")
        else:
            op, v = "=", val
        qc = _qcol({"name": col, "dialect": dialect})
        if qc.get("code") != 200:
            return qc
        ph = _wph({"dialect": dialect, "i": idx})
        if ph.get("code") != 200:
            return ph
        where.append(f"{qc['data']} {op} {ph['data']}")
        a.append(v)
        idx += 1
    return _ok({"where": " where " + " and ".join(where) if where else "", "args": a})


def _check_scalars(data: dict = None) -> Dict[str, Any]:
    """行数据值必须是标量（拒嵌套 dict/list/tuple）。**校验器**：200 通过 / 400 不通过。

    入参 (data): vals(dict, 可选) 待写入的行数据
    返回: {"code":200, "data":{"checked": dict}, "message":"success"} 或 400 错误信封
    """
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_check_scalars")
    vals = data.get("vals")
    if vals is None:
        vals = {}
    if not isinstance(vals, dict):
        return _err(f"vals 必须是字典，收到 {type(vals).__name__}", "_check_scalars")
    for k, v in vals.items():
        if isinstance(v, (dict, list, tuple)):
            return _err(f"列 {k} 的值必须是标量（字符串/数字/布尔/null），不支持嵌套结构",
                        "_check_scalars")
    return _ok({"checked": vals})
