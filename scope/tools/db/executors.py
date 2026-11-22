

"""
各数据库驱动的底层执行器：建连、执行、事务与影响行数钳制。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。

与 dialect.py 分开是**必要的**：dialect 编排调用本层，而上层 _pg/_my 又调用 dialect，
合并成一层会造成循环依赖。
写执行器影响行数超 _MAX_AFFECT 自动回滚；SQLite 只读以 mode=ro URI 打开（连接层即不可写）。
同步驱动（sqlite3）经 asyncio.to_thread 包装，避免阻塞事件循环。

原实现用 `raise ValueError(原因)` 作为"业务校验失败"的信号，靠入口 except ValueError 转 400；
现改为逐层返回 400 信封并显式转发，不再用异常做控制流
（入口仍保留 except ValueError 兜底，防驱动自身抛的 ValueError 变成 500）。
"""


import asyncio
from typing import Any, Dict

from ._helper import _MAX_AFFECT, _err, _ok, _sqlite_target_path



# ---------- PostgreSQL ----------

async def _pg_exec(data: dict = None) -> Dict[str, Any]:
    """PG 建连并执行一条语句（即连即断，无状态）。

    入参 (data):
        cfg(dict, 必填)      连接配置（host/port/user/password）
        database(str, 可选)  目标库，缺省回落 cfg.database，再缺省 postgres
        sql(str, 必填)       语句（占位符用 $1..$n）
        args(list, 可选)     参数化值
        fetch(bool, 可选)    True 取结果集，False 只执行

    返回:
        {"code":200, "data":{"cols": [列名...], "rows": [元组行...]}, "message":"success"}
        fetch=False 时 cols/rows 均为 None
        或 {"code":400, "data": 位置, "message": "错误：<原因>"}
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_pg_exec")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段（连接配置）", "_pg_exec")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_pg_exec")
    if "host" not in cfg:
        return _err("cfg 缺少 host 字段", "_pg_exec")
    sql = data.get("sql")
    if not sql:
        return _err("缺少 sql 字段", "_pg_exec")
    if isinstance(sql, (dict, list, tuple, set)):
        return _err(f"sql 必须是字符串，收到 {type(sql).__name__}", "_pg_exec")
    args = data.get("args")
    if args is not None and not isinstance(args, (list, tuple)):
        return _err(f"args 必须是列表，收到 {type(args).__name__}", "_pg_exec")
    fetch = bool(data.get("fetch", False))
    try:
        import asyncpg
    except ImportError:
        return _err("未安装 asyncpg（pip install asyncpg）", "_pg_exec")
    try:
        conn = await asyncpg.connect(host=cfg["host"], port=int(cfg["port"]),
                                     user=cfg.get("user"), password=cfg.get("password"),
                                     database=data.get("database") or cfg.get("database") or "postgres",
                                     timeout=15)
    except (TypeError, ValueError, OverflowError) as e:
        return _err(f"连接参数无效：{e}", "_pg_exec")
    try:
        if fetch:
            rows = await conn.fetch(str(sql), *(args or []))
            cols = list(rows[0].keys()) if rows else []
            return _ok({"cols": cols, "rows": [tuple(r.values()) for r in rows]})
        await conn.execute(str(sql), *(args or []))
        return _ok({"cols": None, "rows": None})
    finally:
        await conn.close()


async def _pg_write(data: dict = None) -> Dict[str, Any]:
    """PG 事务执行单条写语句，影响行数超上限自动回滚。

    入参 (data): cfg/database/sql/args 同 _pg_exec；cap(int, 可选, 默认 _MAX_AFFECT)
    返回:
        {"code":200, "data":{"affected": int}, "message":"success"}
        {"code":400, ...} 影响行数超 cap（已回滚）
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_pg_write")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_pg_write")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_pg_write")
    if "host" not in cfg:
        return _err("cfg 缺少 host 字段", "_pg_write")
    sql = data.get("sql")
    if not sql:
        return _err("缺少 sql 字段", "_pg_write")
    if isinstance(sql, (dict, list, tuple, set)):
        return _err(f"sql 必须是字符串，收到 {type(sql).__name__}", "_pg_write")
    args = data.get("args")
    if args is not None and not isinstance(args, (list, tuple)):
        return _err(f"args 必须是列表，收到 {type(args).__name__}", "_pg_write")
    raw_cap = data.get("cap", _MAX_AFFECT)
    if isinstance(raw_cap, (dict, list, tuple, set)):
        return _err(f"cap 必须是整数，收到 {type(raw_cap).__name__}", "_pg_write")
    try:
        cap = int(raw_cap if raw_cap not in (None, "") else _MAX_AFFECT)
    except (TypeError, ValueError):
        return _err("cap 必须是整数", "_pg_write")
    try:
        import asyncpg
    except ImportError:
        return _err("未安装 asyncpg（pip install asyncpg）", "_pg_write")
    try:
        conn = await asyncpg.connect(host=cfg["host"], port=int(cfg["port"]),
                                     user=cfg.get("user"), password=cfg.get("password"),
                                     database=data.get("database") or cfg.get("database") or "postgres",
                                     timeout=15)
    except (TypeError, ValueError, OverflowError) as e:
        return _err(f"连接参数无效：{e}", "_pg_write")
    try:
        tr = conn.transaction()
        await tr.start()
        try:
            status = await conn.execute(str(sql), *(args or []))
            n = int(status.split()[-1]) if status else 0
            if n > cap:
                await tr.rollback()
                return _err(f"影响行数 {n} 超过上限 {cap}，已回滚，请缩小筛选范围", "_pg_write")
            await tr.commit()
            return _ok({"affected": n})
        except Exception:
            await tr.rollback()
            raise
    finally:
        await conn.close()


# ---------- MySQL ----------

async def _my_exec(data: dict = None) -> Dict[str, Any]:
    """MySQL 建连并执行一条语句（即连即断）。

    入参 (data): cfg/database/sql/args/fetch 同 _pg_exec（占位符用 %s）
    返回: {"code":200, "data":{"cols":[...],"rows":[...]}, "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_my_exec")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_my_exec")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_my_exec")
    if "host" not in cfg:
        return _err("cfg 缺少 host 字段", "_my_exec")
    sql = data.get("sql")
    if not sql:
        return _err("缺少 sql 字段", "_my_exec")
    if isinstance(sql, (dict, list, tuple, set)):
        return _err(f"sql 必须是字符串，收到 {type(sql).__name__}", "_my_exec")
    args = data.get("args")
    if args is not None and not isinstance(args, (list, tuple)):
        return _err(f"args 必须是列表，收到 {type(args).__name__}", "_my_exec")
    fetch = bool(data.get("fetch", False))
    try:
        import aiomysql
    except ImportError:
        return _err("未安装 aiomysql（pip install aiomysql）", "_my_exec")
    try:
        conn = await aiomysql.connect(host=cfg["host"], port=int(cfg["port"]),
                                      user=cfg.get("user"), password=cfg.get("password"),
                                      db=data.get("database") or cfg.get("database"), autocommit=True)
    except (TypeError, ValueError, OverflowError) as e:
        return _err(f"连接参数无效：{e}", "_my_exec")
    try:
        async with conn.cursor() as cur:
            await cur.execute(str(sql), args or ())
            if fetch:
                rows = await cur.fetchall()
                cols = [d[0] for d in cur.description] if cur.description else []
                return _ok({"cols": cols, "rows": rows})
            return _ok({"cols": None, "rows": None})
    finally:
        conn.close()


async def _my_write(data: dict = None) -> Dict[str, Any]:
    """MySQL 事务执行单条写语句，影响行数超上限自动回滚。

    入参 (data): cfg/database/sql/args/cap 同 _pg_write
    返回: {"code":200, "data":{"affected": int}, "message":"success"} 或 400（已回滚）
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_my_write")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_my_write")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_my_write")
    if "host" not in cfg:
        return _err("cfg 缺少 host 字段", "_my_write")
    sql = data.get("sql")
    if not sql:
        return _err("缺少 sql 字段", "_my_write")
    if isinstance(sql, (dict, list, tuple, set)):
        return _err(f"sql 必须是字符串，收到 {type(sql).__name__}", "_my_write")
    args = data.get("args")
    if args is not None and not isinstance(args, (list, tuple)):
        return _err(f"args 必须是列表，收到 {type(args).__name__}", "_my_write")
    raw_cap = data.get("cap", _MAX_AFFECT)
    if isinstance(raw_cap, (dict, list, tuple, set)):
        return _err(f"cap 必须是整数，收到 {type(raw_cap).__name__}", "_my_write")
    try:
        cap = int(raw_cap if raw_cap not in (None, "") else _MAX_AFFECT)
    except (TypeError, ValueError):
        return _err("cap 必须是整数", "_my_write")
    try:
        import aiomysql
    except ImportError:
        return _err("未安装 aiomysql（pip install aiomysql）", "_my_write")
    try:
        conn = await aiomysql.connect(host=cfg["host"], port=int(cfg["port"]),
                                      user=cfg.get("user"), password=cfg.get("password"),
                                      db=data.get("database") or cfg.get("database"), autocommit=False)
    except (TypeError, ValueError, OverflowError) as e:
        return _err(f"连接参数无效：{e}", "_my_write")
    try:
        async with conn.cursor() as cur:
            await cur.execute(str(sql), args or ())
            n = cur.rowcount
        if n > cap:
            await conn.rollback()
            return _err(f"影响行数 {n} 超过上限 {cap}，已回滚，请缩小筛选范围", "_my_write")
        await conn.commit()
        return _ok({"affected": n})
    except Exception:
        await conn.rollback()
        raise
    finally:
        conn.close()


# ---------- SQLite ----------

def _lt_read_run(data: dict = None) -> Dict[str, Any]:
    """同步 sqlite3 读执行（在线程内跑）。mode=ro URI 打开——连接层即无法写库。

    入参 (data): path(str, 必填), sql(str, 必填), params(list, 可选), fetch(bool, 可选)
    返回: {"code":200, "data":{"cols":[...],"rows":[...]}, "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_lt_read_run")
    path = data.get("path")
    if not path:
        return _err("缺少 path 字段", "_lt_read_run")
    sql = data.get("sql")
    if not sql:
        return _err("缺少 sql 字段", "_lt_read_run")
    params = data.get("params")
    if params is not None and not isinstance(params, (list, tuple)):
        return _err(f"params 必须是列表，收到 {type(params).__name__}", "_lt_read_run")
    fetch = bool(data.get("fetch", False))
    import pathlib
    import sqlite3
    try:
        uri = pathlib.Path(str(path)).resolve().as_uri() + "?mode=ro"
    except (TypeError, ValueError, OSError) as e:
        return _err(f"路径无法转为 URI：{e}", "_lt_read_run")
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=15)
    except sqlite3.Error as e:
        return _err(f"SQLite 只读连接失败：{e}", "_lt_read_run")
    try:
        cur = conn.cursor()
        cur.execute(str(sql), params or [])
        if fetch:
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
            return _ok({"cols": cols, "rows": rows})
        return _ok({"cols": None, "rows": None})
    except sqlite3.Error as e:
        return _err(f"SQLite 读执行失败：{type(e).__name__}: {e}", "_lt_read_run")
    finally:
        conn.close()


async def _lt_exec(data: dict = None) -> Dict[str, Any]:
    """SQLite 只读执行：解析目标文件 → 线程内 mode=ro 执行。

    入参 (data): cfg/database/sql/args/fetch 同 _pg_exec
    返回: {"code":200, "data":{"cols":[...],"rows":[...]}, "message":"success"}
          或 400 错误信封（路径解析失败由 _sqlite_target_path 直接转发，不再 raise ValueError）
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_lt_exec")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_lt_exec")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_lt_exec")
    tp = _sqlite_target_path({"cfg": cfg, "database": data.get("database")})
    if tp.get("code") != 200:
        return tp                      # 显式转发，原实现是 raise ValueError 交给入口
    return await asyncio.to_thread(
        _lt_read_run,
        {"path": tp["data"]["path"], "sql": data.get("sql"),
         "params": data.get("args"), "fetch": bool(data.get("fetch", False))})


def _lt_write_run(data: dict = None) -> Dict[str, Any]:
    """同步 sqlite3 写执行（在线程内跑）。显式事务，影响行数超上限自动回滚。

    入参 (data): path(str, 必填), sql(str, 必填), params(list, 可选), cap(int, 必填)
    返回: {"code":200, "data":{"affected": int}, "message":"success"} 或 400（已回滚）
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_lt_write_run")
    path = data.get("path")
    if not path:
        return _err("缺少 path 字段", "_lt_write_run")
    sql = data.get("sql")
    if not sql:
        return _err("缺少 sql 字段", "_lt_write_run")
    params = data.get("params")
    if params is not None and not isinstance(params, (list, tuple)):
        return _err(f"params 必须是列表，收到 {type(params).__name__}", "_lt_write_run")
    raw_cap = data.get("cap")
    if raw_cap is None:
        raw_cap = _MAX_AFFECT
    if isinstance(raw_cap, (dict, list, tuple, set)):
        return _err(f"cap 必须是整数，收到 {type(raw_cap).__name__}", "_lt_write_run")
    try:
        cap = int(raw_cap)
    except (TypeError, ValueError):
        return _err("cap 必须是整数", "_lt_write_run")
    import sqlite3
    try:
        conn = sqlite3.connect(str(path), timeout=15)
    except sqlite3.Error as e:
        return _err(f"SQLite 写连接失败：{e}", "_lt_write_run")
    try:
        conn.isolation_level = None
        cur = conn.cursor()
        cur.execute("begin")
        try:
            cur.execute(str(sql), params or [])
            n = cur.rowcount if cur.rowcount is not None else 0
            if n > cap:
                cur.execute("rollback")
                return _err(f"影响行数 {n} 超过上限 {cap}，已回滚，请缩小筛选范围", "_lt_write_run")
            cur.execute("commit")
            return _ok({"affected": n})
        except sqlite3.Error as e:
            cur.execute("rollback")
            return _err(f"SQLite 写执行失败：{type(e).__name__}: {e}", "_lt_write_run")
        except Exception:
            cur.execute("rollback")
            raise
    finally:
        conn.close()


async def _lt_write(data: dict = None) -> Dict[str, Any]:
    """SQLite 写执行：解析目标文件（for_write=True，文件须已存在）→ 线程内事务执行。

    入参 (data): cfg/database/sql/args/cap
    返回: {"code":200, "data":{"affected": int}, "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_lt_write")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_lt_write")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_lt_write")
    raw_cap = data.get("cap", _MAX_AFFECT)
    if isinstance(raw_cap, (dict, list, tuple, set)):
        return _err(f"cap 必须是整数，收到 {type(raw_cap).__name__}", "_lt_write")
    try:
        cap = int(raw_cap if raw_cap not in (None, "") else _MAX_AFFECT)
    except (TypeError, ValueError):
        return _err("cap 必须是整数", "_lt_write")
    tp = _sqlite_target_path({"cfg": cfg, "database": data.get("database"), "for_write": True})
    if tp.get("code") != 200:
        return tp
    return await asyncio.to_thread(
        _lt_write_run,
        {"path": tp["data"]["path"], "sql": data.get("sql"),
         "params": data.get("args"), "cap": cap})


# ---------- MongoDB ----------

def _mongo_call(data: dict = None) -> Dict[str, Any]:
    """同步 pymongo 调用放到当前线程执行（调用方负责 to_thread）。

    入参 (data):
        cfg(dict, 必填)      连接配置（host/port/user/password）
        fn(callable, 必填)   fn(client) → 结果
        database(str, 可选)  **原实现有此参数但未使用**（URI 不含库名，由 fn 内部自行
                             client[database]）；保留以不破坏调用方（mongodb.py）的传参习惯

    返回: {"code":200, "data": fn 的返回值, "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_mongo_call")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_mongo_call")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_mongo_call")
    if "host" not in cfg:
        return _err("cfg 缺少 host 字段", "_mongo_call")
    fn = data.get("fn")
    if fn is None:
        return _err("缺少 fn 字段（fn(client) → 结果 的回调）", "_mongo_call")
    if not callable(fn):
        return _err(f"fn 必须可调用，收到 {type(fn).__name__}", "_mongo_call")
    try:
        from pymongo import MongoClient
    except ImportError:
        return _err("未安装 pymongo（pip install pymongo）", "_mongo_call")
    host = str(cfg["host"])
    try:
        port = str(int(cfg["port"]))
    except (KeyError, TypeError, ValueError):
        return _err(f"cfg.port 必须是整数，收到 {cfg.get('port')!r}", "_mongo_call")
    user = str(cfg.get("user") or "")
    pwd = str(cfg.get("password") or "")
    if user:
        uri = "mongodb://" + user + ":" + pwd + "@" + host + ":" + port + "/"
    else:
        uri = "mongodb://" + host + ":" + port + "/"
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    except Exception as e:
        return _err(f"MongoClient 构建失败：{type(e).__name__}: {e}", "_mongo_call")
    try:
        return _ok(fn(client))
    finally:
        client.close()
