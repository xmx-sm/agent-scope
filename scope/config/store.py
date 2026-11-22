# -*- coding: utf-8 -*-
"""config.db（SQLite）读写 + 进程级缓存。

设计要点
────────────────────────────────────────────────────────────────
1. **同步读一次、之后走内存**：SQLite 是同步 IO，而工具链全异步。故不在每次
   get 时查库——`load()` 一次性把全表读进进程级缓存 `_CACHE`，此后 `get()` 是
   纯内存操作（同步、无 IO）。装配层在启动时调一次 `load()`（或 `await aload()`），
   即不违反铁律 #8「同步阻塞 IO 一律 asyncio.to_thread 包装」。
   未预载时首次 get 会惰性同步 load 一次并记 warning（本地文件几十毫秒，可接受，
   但线上应在装配期显式预载）。

2. **值用 JSON 编码存 TEXT**：保证 int/float/bool/list/dict/None 类型保真，
   避免 SQLite 动态类型把 "30" 与 30 混淆、True 与 "True" 混淆。

3. **优先级在调用方合并**：本层只负责"从库读一个 key"，
   `data > sqlite > None` 的合并由各域自己做（因为它们要知道每个字段的语义）。
   取不到返回 None，由各函数原有逻辑决定是报错还是回落。

4. **敏感项**：schema 里 secret=True 的项（密码/账号）出厂值为 None，
   库里存的是 JSON null；部署方手动 `set()` 或 UPDATE 库注入真实值。
   config.db 已列入 .gitignore，绝不入库。
"""

import asyncio
import json
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from . import schema as _schema

# 默认库路径：本目录下 config.db（被 .gitignore）
_DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.db")

# 进程级状态
_DB_PATH: str = _DEFAULT_DB
_CACHE: Optional[Dict[str, Any]] = None          # None=未载入；dict=已载入
# RLock 而非 Lock：load() 持锁时会调 init_db()，后者结尾也要抢同一把锁清缓存，
# 非重入 Lock 会死锁（"configure 到新路径后首次 set_value → load → init_db"路径触发过）。
_LOCK = threading.RLock()
_LOADED_FROM: Optional[str] = None                # 缓存来自哪个库路径


def _where(fn: str) -> str:
    return f"{os.path.abspath(__file__)}_{fn}"


# ── 库路径与初始化 ───────────────────────────────────────────────
def configure(db_path: Optional[str] = None) -> str:
    """设置本进程使用的 config.db 路径；改路径会使缓存失效（下次 load 重读）。

    返回生效路径。db_path=None 恢复为默认（本目录 config.db）。
    """
    global _DB_PATH, _CACHE, _LOADED_FROM
    with _LOCK:
        new = db_path or _DEFAULT_DB
        if new != _DB_PATH:
            _DB_PATH = new
            _CACHE = None
            _LOADED_FROM = None
        return _DB_PATH


def db_path() -> str:
    """当前生效的库路径。"""
    return _DB_PATH


def init_db(path: Optional[str] = None, reset: bool = False) -> str:
    """建表并从 schema 灌入出厂默认值。幂等（除非 reset=True 清空重灌）。

    reset=True 会**删除全部现有配置行**再重灌——会丢掉部署方手动注入的敏感值，
    仅用于首次建库或明确要恢复出厂。

    返回库路径。
    """
    p = path or _DB_PATH
    if path and path != _DB_PATH:
        configure(path)
    parent = os.path.dirname(os.path.abspath(p))
    if parent:
        # configure 到含新目录的路径时，sqlite3.connect 不会建多级父目录（unable to open database file）
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(p, timeout=15)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS config (
                   key      TEXT PRIMARY KEY,
                   value    TEXT,                 -- JSON 编码；NULL 表示未配
                   type     TEXT NOT NULL,        -- 期望类型（校验用）
                   category TEXT NOT NULL,
                   note     TEXT,
                   secret   INTEGER NOT NULL DEFAULT 0
                )"""
        )
        if reset:
            conn.execute("DELETE FROM config")
        for it in _schema.ALL:
            val = _expand_default(it)
            payload = json.dumps(val, ensure_ascii=False)
            # INSERT OR IGNORE：已有行（含部署方改过的值）不被出厂值覆盖
            conn.execute(
                "INSERT OR IGNORE INTO config (key, value, type, category, note, secret) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (it.key, payload, it.type, it.category, it.note, 1 if it.secret else 0),
            )
        conn.commit()
    finally:
        conn.close()
    # 建库后缓存失效，下次 load 重读
    global _CACHE, _LOADED_FROM
    with _LOCK:
        _CACHE = None
        _LOADED_FROM = None
    return p


def _expand_default(it: "_schema.Item") -> Any:
    """展开出厂默认：个别 key 的 None 需在灌库时按运行时上下文补全。

    mcp.config_path 的默认是"本包目录下的 mcp_servers.json"，含 __file__，
    不能在 schema 里硬编码，故在此展开。其余 None 原样存 JSON null。
    """
    if it.key == "mcp.config_path" and it.value is None:
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "tools", "mcp", "mcp_servers.json",
        )
    return it.value


# ── 载入与读取 ───────────────────────────────────────────────────
def _table_exists(p: str) -> bool:
    """库文件里是否有 config 表（防文件存在但表被删的历史库）。"""
    try:
        conn = sqlite3.connect(p, timeout=15)
        try:
            return conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='config'"
            ).fetchone() is not None
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def load(force: bool = False) -> Dict[str, Any]:
    """从库读全表进缓存，返回缓存 dict 的引用。幂等；force=True 强制重读。

    库不存在时自动 init_db() 再读（首次使用即"just works"，无需单独建库步骤）。
    """
    global _CACHE, _LOADED_FROM
    with _LOCK:
        if _CACHE is not None and not force and _LOADED_FROM == _DB_PATH:
            return _CACHE
        # 文件不存在，或文件在但 config 表被删（历史库/手工清表）→ 建库灌出厂默认
        if not os.path.exists(_DB_PATH) or not _table_exists(_DB_PATH):
            init_db()
        conn = sqlite3.connect(_DB_PATH, timeout=15)
        try:
            rows = conn.execute("SELECT key, value FROM config").fetchall()
        finally:
            conn.close()
        cache: Dict[str, Any] = {}
        for k, v in rows:
            if v is None:
                cache[k] = None
            else:
                try:
                    cache[k] = json.loads(v)
                except (TypeError, ValueError):
                    cache[k] = v          # 非 JSON（历史脏数据）原样保留
        _CACHE = cache
        _LOADED_FROM = _DB_PATH
        return _CACHE


async def aload(force: bool = False) -> Dict[str, Any]:
    """load() 的异步版：同步 IO 放线程里（铁律 #8）。装配期用这个预载。"""
    return await asyncio.to_thread(load, force)


def get(key: str, default: Any = None) -> Any:
    """读一个配置项的生效值。

    - 库里有非 null 值 → 返回它
    - 库里是 null（敏感项未注入）或 key 不存在 → 返回 default（缺省 None）

    未预载时惰性 load 一次（同步 IO）。返回 None 不报错——由各域函数决定
    是回落、报错还是当作"未配置"。
    """
    cache = _CACHE
    if cache is None or _LOADED_FROM != _DB_PATH:
        cache = load()
    v = cache.get(key, None)
    return default if v is None else v


def clamp_get(key: str, hard_max: Any) -> Any:
    """读**钳制上限**类配置项，强制"只收紧不放宽"（铁律 #11）。

    返回 min(sqlite值, hard_max)：库里调小生效（更严），调大无效（被 hard_max 压回）。
    hard_max 是源码常量，代表该能力的绝对上限，绝不因数据源而松动。

    - sqlite 无值 / 为 null → 返回 hard_max（出厂即上限）
    - sqlite 值 > hard_max → 返回 hard_max（放宽无效）
    - sqlite 值 ≤ hard_max → 返回 sqlite 值（收紧生效）

    仅对数值型（int/float）有意义。hard_max 项在 schema 里标了 hard_max 字段，
    消费点必须用本函数而非 get()。
    """
    v = get(key, None)
    if v is None:
        return hard_max
    try:
        return type(hard_max)(min(v, hard_max)) if v > hard_max else v
    except (TypeError, ValueError):
        return hard_max          # 库里是坏类型，回落到硬上限（fail-safe：宁严不宁松）


async def aget(key: str, default: Any = None) -> Any:
    """get 的异步版（内部仍是内存读，仅为与 async 域函数签名一致；不额外 to_thread）。"""
    return get(key, default)


def set_value(key: str, value: Any, persist: bool = True) -> bool:
    """写一个配置项。persist=True 落库并更新缓存；False 仅改缓存（本进程临时覆盖）。

    按 schema 声明类型软校验：类型不符仍写入但记入返回 False 供调用方察觉？
    不——用户要求"参数错误正常报错"，故类型不符**抛 TypeError**（这是配置管理
    函数的入参错误，属编程错误，应尽早崩，与各域"业务校验返回 400"不同层）。
    """
    it = _schema.BY_KEY.get(key)
    if it is None:
        raise KeyError(f"未知配置项: {key!r}（合法 key 见 schema.ALL）")
    _check_type(key, value, it.type)
    payload = None if value is None else json.dumps(value, ensure_ascii=False)
    if persist:
        load()   # 确保库表存在（configure 到新路径后首次写，靠 load 的惰性 init_db 建表）
        conn = sqlite3.connect(_DB_PATH, timeout=15)
        try:
            conn.execute(
                "INSERT INTO config (key, value, type, category, note, secret) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, payload, it.type, it.category, it.note, 1 if it.secret else 0),
            )
            conn.commit()
        finally:
            conn.close()
    # 更新缓存（若已载入）
    if _CACHE is not None:
        _CACHE[key] = value
    return True


def _check_type(key: str, value: Any, typ: str) -> None:
    if value is None:
        return
    expect = {
        "str": (str,), "int": (int,), "float": (int, float),
        "bool": (bool,), "list": (list,), "dict": (dict,), "any": None,
    }.get(typ)
    if expect is None:
        return
    # bool 是 int 子类，int 项要排除 bool 误入
    if typ == "int" and isinstance(value, bool):
        raise TypeError(f"配置项 {key!r} 期望 int，收到 bool")
    if not isinstance(value, expect):
        raise TypeError(f"配置项 {key!r} 期望 {typ}，收到 {type(value).__name__}")


def unset(key: str) -> None:
    """把某 key 恢复为出厂默认（删行后由 init_db 重灌，或直接重置为 schema 值）。"""
    it = _schema.BY_KEY.get(key)
    if it is None:
        raise KeyError(f"未知配置项: {key!r}")
    set_value(key, _expand_default(it))


def all_values() -> Dict[str, Any]:
    """当前生效的全量配置快照（缓存值，含 null 项）。"""
    return dict(load())


def categories() -> List[str]:
    return sorted({it.category for it in _schema.ALL})


def items_by_category(category: str) -> List["_schema.Item"]:
    return [it for it in _schema.ALL if it.category == category]


def schema_keys() -> List[str]:
    return [it.key for it in _schema.ALL]
