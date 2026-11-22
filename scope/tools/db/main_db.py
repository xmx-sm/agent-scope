

"""
db 工具统一入口与 function 路由（PostgreSQL / MySQL / MongoDB / SQLite）。

原 async_db_tools.py 拆分而来。本文件只保留两个入口与 function 白名单，
无状态辅助、安全闸门、驱动执行、方言编排各归其模块。

调用契约（务必留意，易错）:
    - 业务参数**平铺在 data 顶层**，不嵌在 arguments 子字典里
    - 返回信封 {"code":200|400|500, "data":..., "message":...}，错误字段名是 message 不是 msg
    - 写工具的行数据键是 "data"，不是 "values"
    - 经 agentscope FunctionTool 调用时，模型须传 {"data": {...}}（call_tool 会展开成 kwargs）

分层（自底向上，无环）:
    _helper.py      无状态辅助：常量与上限、正则、返回信封 _err/_ok、
                    连接配置归一化、SQLite 路径解析、标识符/占位符/值翻译
    gate.py         库级/表级白名单黑名单与 SQL 表引用校验（fail-closed，业务核心）
    executors.py    各驱动的连接与事务（影响行数超限自动回滚）
    dialect.py      SQL 方言编排：结构化取数、只读 SQL、写 SQL
    postgresql.py   _pg    mysql.py  _my    sqlite.py  _lite    mongodb.py  _mongo/_mongo_write
    main_db.py      本文件，两个入口

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封；
参数错误一律 if 判断后返回 code 400，不裸抛。
"""

from typing import Any, Dict

from ._helper import _db_allowed, _err, _ok, _resolve, _target_db
from .dialect import _sql_dialect_write
from .gate import _db_gate, _db_same, _tbl_filter_out, _tbl_list
from .mongodb import _mongo, _mongo_write
from .mysql import _my
from .postgresql import _pg
from .sqlite import _lite


FUNCTIONS = ("list_databases", "list_tables", "describe_table",
             "table_data", "count_table", "run_query")

WRITE_FUNCTIONS = ("insert_row", "update_rows", "delete_rows", "run_write")


async def async_db_write_tools(data: dict = None) -> Dict[str, Any]:
    """
    数据库写操作统一入口（异步；PostgreSQL/MySQL/MongoDB/SQLite）。高危工具，平台可按工具级权限停用。
    SQLite：db_config 传 db_type="sqlite" + path（单数据库文件）或 dir（文件夹，database=文件名）；
    写操作只作用于已存在的库文件；allow_write=false 同样整体拒绝。
    写入前先用 async_db_tools 查结构与数据，执行前向用户复述变更，执行后报告影响行数。

    支持的 function（data["function"]，连接用 data["db_config"] 或平台凭证注入）:
        insert_row   {database?, table, data:{列名:值}}       插入一条记录
        update_rows  {database?, table, filters, data:{列名:值}}
                     按条件更新：filters 必传且非空（等值/{"like":"%x%"}/{"gte":n}/{"lte":n}，AND 拼接）
        delete_rows  {database?, table, filters}              按条件删除：filters 必传且非空，禁止全表删除
        run_write    {database?, sql}                          单条 insert/update/delete 原始语句
                     （update/delete 必须含 WHERE；DDL/多语句拒绝；mongodb 不支持）

    安全约束：影响行数超过 100 自动回滚报错；update/delete 无条件拒绝；
    表名/列名标识符校验、值全部参数化传递防注入；db_config.allow_write=false 时本工具全部操作拒绝；
    db_config.allowed_tables/denied_tables 表级管控同样约束写操作（run_write 需可完整解析出引用表）。
    返回: {"code":200,"data":{"affected":N,...},"message":"success"}；校验错误 400；连接执行失败 500
    """
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _err(f"data 必须是字典对象，收到 {type(data).__name__}", "async_db_write_tools")
    function = str(data.get("function") or "").strip().lower()
    if function not in WRITE_FUNCTIONS:
        return _err(f"未知 function: {function or '(空)'}，支持: {', '.join(WRITE_FUNCTIONS)}",
                    "async_db_write_tools")
    args = {k: data[k] for k in ("database", "table", "filters", "data", "sql") if k in data}
    rs = _resolve(data)
    if rs.get("code") != 200:
        return rs
    db_type, cfg = rs["data"]["db_type"], rs["data"]["cfg"]
    gr = _db_gate({"cfg": cfg, "args": args, "write": True})
    if gr.get("code") != 200:
        return gr                          # 闸门拒绝，直接转发 400 信封
    try:
        if db_type == "postgresql":
            return await _sql_dialect_write({"dialect": "pg", "cfg": cfg, "args": args,
                                            "function": function})
        if db_type == "mysql":
            return await _sql_dialect_write({"dialect": "mysql", "cfg": cfg, "args": args,
                                            "function": function})
        if db_type == "sqlite":
            return await _sql_dialect_write({"dialect": "sqlite", "cfg": cfg, "args": args,
                                            "function": function})
        return await _mongo_write({"function": function, "cfg": cfg, "args": args})
    except ValueError as e:
        # 兜底：MongoDB 线程内回调超限用 raise 传播（线程返回值无法回传错误信封），
        # 以及驱动自身抛的 ValueError。业务校验失败现已走 400 信封，不经此处。
        return _err(str(e), "async_db_write_tools")
    except Exception as e:
        return {"code": 500, "data": f"{__file__}_async_db_write_tools",
                "message": f"数据库写操作失败：{type(e).__name__}: {e}"}


async def async_db_tools(data: dict = None) -> Dict[str, Any]:
    """
    数据库只读查询统一入口（异步；PostgreSQL/MySQL/MongoDB/SQLite）。
    data["function"] 决定操作，连接用 data["db_config"]（或平台凭证注入/顶层字段）。
    写操作（增删改）在独立工具 async_db_write_tools，本工具仅只读。
    SQLite：db_config 传 db_type="sqlite" + path（单数据库文件）或 dir（sqlite 文件夹，
    database=文件夹内文件名、可省后缀）；list_databases 在文件夹模式下枚举库文件；
    只读连接 mode=ro，attach/detach/pragma 一律拒绝。

    支持的 function:
        list_databases                          列出所有数据库
        list_tables   {database?, pattern?}     列出表/集合，pattern 支持 % 通配筛选
        describe_table {database?, table}       查看表结构（列/类型/可空/默认值）
        table_data    {database?, table, filters?, columns?, order_by?, offset?, limit?}
                                                分页取数：filters 支持等值与 {"like":"%x%"}/{"gte":n}/{"lte":n}；
                                                order_by "列名" 或 "列名:desc"；limit≤500
        count_table   {database?, table, filters?}  筛选后总行数
        run_query     {database?, sql, limit?}  只读 SQL（select/with/show/desc/explain 开头，禁写；
                                                启用表级管控时仅允许单条 select/with，且 SQL 引用的
                                                每张表都必须在可读范围，解析失败即拒绝）

        增/删/改请使用独立工具 async_db_write_tools（insert_row/update_rows/delete_rows/run_write）

    示例: {"function": "list_tables", "db_config": {...}, "pattern": "%user%"}
    返回: {"code":200,"data":..., "message":"success"}；参数/权限错误 400；连接执行失败 500
    """
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _err(f"data 必须是字典对象，收到 {type(data).__name__}", "async_db_tools")
    function = str(data.get("function") or "").strip().lower()
    if function not in FUNCTIONS:
        return _err(f"未知 function: {function or '(空)'}，支持: {', '.join(FUNCTIONS)}",
                    "async_db_tools")
    # 顶层业务参数归一
    args = {k: data[k] for k in ("database", "pattern", "table", "filters", "columns",
                                 "order_by", "offset", "limit", "sql") if k in data}
    rs = _resolve(data)
    if rs.get("code") != 200:
        return rs
    db_type, cfg = rs["data"]["db_type"], rs["data"]["cfg"]
    if function != "list_databases":
        gr = _db_gate({"cfg": cfg, "args": args})
        if gr.get("code") != 200:
            return gr                      # 闸门拒绝，直接转发 400 信封
    try:
        if db_type == "postgresql":
            out = await _pg({"function": function, "cfg": cfg, "args": args})
        elif db_type == "mysql":
            out = await _my({"function": function, "cfg": cfg, "args": args})
        elif db_type == "sqlite":
            out = await _lite({"function": function, "cfg": cfg, "args": args})
        else:
            out = await _mongo({"function": function, "cfg": cfg, "args": args})
        if out.get("code") != 200:
            return out                     # 方言层错误，直接转发（原实现靠 isinstance(out, str)）
        data_out = out["data"]
        if function == "list_tables":
            td = _target_db({"cfg": cfg, "args": args})
            if td.get("code") != 200:
                return td
            fo = _tbl_filter_out({"cfg": cfg, "target": td["data"], "out": data_out})
            if fo.get("code") != 200:
                return fo
            data_out = fo["data"]
        if function == "list_databases" and isinstance(data_out, list):
            al = _db_allowed({"cfg": cfg})
            if al.get("code") != 200:
                return al
            allow = al["data"]
            if allow:
                # 与下方黑名单共用 _db_same（SQLite 文件模式去后缀互认）：
                # folder 模式下调用写 "orders"、文件名是 "orders.db" 时也能正确列出。
                data_out = [x for x in data_out
                            if any(_db_same({"a": a, "b": x})["data"] for a in allow)]
            dl = _tbl_list({"cfg": cfg, "key": "denied_databases"})
            if dl.get("code") != 200:
                return dl
            deny_dbs = dl["data"]
            if deny_dbs:
                kept = []
                for x in data_out:
                    hit = False
                    for e in deny_dbs:
                        dr = _db_same({"a": e, "b": x})
                        if dr.get("code") != 200:
                            return dr
                        if dr["data"]:
                            hit = True
                            break
                    if not hit:
                        kept.append(x)
                data_out = kept
        return _ok(data_out)
    except ValueError as e:
        return _err(str(e), "async_db_tools")
    except Exception as e:
        return {"code": 500, "data": f"{__file__}_async_db_tools",
                "message": f"数据库查询失败：{type(e).__name__}: {e}"}


__all__ = ["async_db_tools", "async_db_write_tools"]
