

"""
MongoDB 入口 _mongo / _mongo_write：集合与文档操作走 PyMongo，不支持原始 SQL。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。

原实现在**线程内回调**里调 _mongo_filters，校验失败无法传播回主线程；
现提到主线程预计算（filters 不依赖 client，提前算完全等价），错误可正常返回 400。
未知 function 原返回 None 会被入口当成功处理，现改 400。
"""

import asyncio
import re
from typing import Any, Dict

from ._helper import _MAX_AFFECT, _MAX_ROWS, _err, _mongo_filters
from .executors import _mongo_call


def _bad_limit(data: dict = None):
    """limit/offset 归一化校验。**内部小工具**：返回 (值, None) 或 (None, 错误信封)。

    入参 (data): args(dict 必填，业务参数), fn_name(str 可选), field(str 必填), default(int 可选)

    不套信封——它同时回传"值"与"错误信封"两种东西，套信封反而要调用方再解一层。
    与 _ok/_err 同属"信封机器"，故豁免 data 入参之外的统一规则（入参仍是 data）。
    """
    if not isinstance(data, dict):
        return None, _err("data 必须是字典对象", "_bad_limit")
    args = data.get("args")
    if args is None:
        return None, _err("缺少 args 字段（业务参数）", "_bad_limit")
    if not isinstance(args, dict):
        return None, _err(f"args 必须是字典，收到 {type(args).__name__}", "_bad_limit")
    field = data.get("field")
    if not field:
        return None, _err("缺少 field 字段（要读的键名）", "_bad_limit")
    fn_name = str(data.get("fn_name") or "_bad_limit")
    raw_default = data.get("default", 0)
    if isinstance(raw_default, (dict, list, tuple, set)):
        return None, _err(f"default 必须是整数，收到 {type(raw_default).__name__}", fn_name)
    raw = args.get(field, raw_default)
    if raw in (None, ""):
        raw = raw_default
    if isinstance(raw, (dict, list, tuple, set)):
        return None, _err(f"{field} 必须是整数，收到 {type(raw).__name__}", fn_name)
    try:
        return int(raw), None
    except (TypeError, ValueError):
        return None, _err(f"{field} 必须是整数", fn_name)


async def _mongo(data: dict = None) -> Dict[str, Any]:
    """MongoDB 只读操作分发。

    入参 (data):
        function(str, 必填)  list_databases / list_tables / describe_table /
                            table_data / count_table（run_query 不支持）
        cfg(dict, 必填)      已归一化的连接配置
        args(dict, 可选)     业务参数（database/pattern/table/filters/limit/offset）

    返回: {"code":200, "data": <该 function 的结果>, "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_mongo")
    function = data.get("function")
    if not function:
        return _err("缺少 function 字段", "_mongo")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_mongo")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_mongo")
    args = data.get("args")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return _err(f"args 必须是字典，收到 {type(args).__name__}", "_mongo")
    db = args.get("database") or cfg.get("database")

    if function == "list_databases":
        def run(client):
            try:
                return sorted(client.list_database_names())
            except Exception:
                return [d for d in ([cfg.get("database")] if cfg.get("database") else [])]
        return await asyncio.to_thread(_mongo_call, {"cfg": cfg, "database": db, "fn": run})
    if function == "list_tables":
        def run(client):
            d = client[args.get("database") or cfg.get("database") or "admin"]
            pat = args.get("pattern")
            names = d.list_collection_names()
            if pat and pat != "%":
                rx = re.compile(str(pat).replace("%", ".*"), re.I)
                names = [n for n in names if rx.search(n)]
            return sorted(names)[:200]
        return await asyncio.to_thread(_mongo_call, {"cfg": cfg, "database": db, "fn": run})
    if function == "describe_table":
        table = args.get("table")
        if not table:
            return _err("缺少 table 字段（集合名）", "_mongo")
        def run(client):
            col = client[db or "admin"][table]
            doc = col.find_one() or {}
            return [{"column": k, "type": type(v).__name__} for k, v in doc.items()]
        return await asyncio.to_thread(_mongo_call, {"cfg": cfg, "database": db, "fn": run})
    if function == "table_data":
        limit, e = _bad_limit({"args": args, "fn_name": "_mongo", "field": "limit",
                            "default": 50})
        if e:
            return e
        offset, e = _bad_limit({"args": args, "fn_name": "_mongo", "field": "offset",
                             "default": 0})
        if e:
            return e
        limit, offset = min(limit, _MAX_ROWS), max(offset, 0)
        mf = _mongo_filters({"spec": args.get("filters")})
        if mf.get("code") != 200:
            return mf
        flt = mf["data"]
        if not args.get("table"):
            return _err("缺少 table 字段（集合名）", "_mongo")
        def run(client):
            col = client[db or "admin"][args["table"]]
            cursor = col.find(flt).skip(offset).limit(limit)
            rows = []
            for doc in cursor:
                if "_id" in doc:
                    doc["_id"] = str(doc["_id"])
                rows.append(doc)
            return {"rows": rows, "returned": len(rows), "limit": limit, "offset": offset}
        return await asyncio.to_thread(_mongo_call, {"cfg": cfg, "database": db, "fn": run})
    if function == "count_table":
        if not args.get("table"):
            return _err("缺少 table 字段（集合名）", "_mongo")
        mf = _mongo_filters({"spec": args.get("filters")})
        if mf.get("code") != 200:
            return mf
        flt = mf["data"]
        def run(client):
            col = client[db or "admin"][args["table"]]
            return {"count": col.count_documents(flt)}
        return await asyncio.to_thread(_mongo_call, {"cfg": cfg, "database": db, "fn": run})
    if function == "run_query":
        return _err("mongodb 不支持 run_query，请使用 table_data/filters 查询", "_mongo")
    return _err(f"_mongo 不支持的 function: {function}", "_mongo")


async def _mongo_write(data: dict = None) -> Dict[str, Any]:
    """MongoDB 写操作分发。

    入参 (data):
        function(str, 必填)  insert_row / update_rows / delete_rows（run_write 不支持）
        cfg(dict, 必填)      已归一化的连接配置
        args(dict, 可选)     业务参数（table/data/filters）

    返回: {"code":200, "data":{"collection":...,"affected":int,...}, "message":"success"}
          或 400 错误信封（匹配数超 _MAX_AFFECT 时不做修改）
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_mongo_write")
    function = data.get("function")
    if not function:
        return _err("缺少 function 字段", "_mongo_write")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "_mongo_write")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "_mongo_write")
    args = data.get("args")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return _err(f"args 必须是字典，收到 {type(args).__name__}", "_mongo_write")
    db = args.get("database") or cfg.get("database")
    table = str(args.get("table") or "").strip()

    if function == "run_write":
        return _err("mongodb 不支持 run_write，请使用 insert_row/update_rows/delete_rows",
                    "_mongo_write")
    if not table:
        return _err("table（集合名）不能为空", "_mongo_write")
    if function == "insert_row":
        docs = args.get("data")
        if not isinstance(docs, (dict, list)) or not docs:
            return _err("data 必须是非空文档对象（或文档数组批量插入）", "_mongo_write")

        def run_ins(client):
            col = client[db or "admin"][table]
            if isinstance(docs, list):
                r = col.insert_many(docs)
                return {"collection": table, "affected": len(r.inserted_ids)}
            r = col.insert_one(docs)
            return {"collection": table, "affected": 1, "inserted_id": str(r.inserted_id)}
        return await asyncio.to_thread(_mongo_call, {"cfg": cfg, "database": db, "fn": run_ins})

    flt_raw = args.get("filters")
    if not isinstance(flt_raw, dict) or not flt_raw:
        return _err("update/delete 必须携带非空 filters，禁止全表操作", "_mongo_write")
    mf = _mongo_filters({"spec": flt_raw})
    if mf.get("code") != 200:
        return mf
    flt = mf["data"]
    if function == "update_rows":
        vals = args.get("data")
        if not isinstance(vals, dict) or not vals:
            return _err("data（新字段值 {字段: 值}）不能为空", "_mongo_write")

        def run_upd(client):
            col = client[db or "admin"][table]
            n0 = col.count_documents(flt)
            if n0 == 0:
                return {"collection": table, "matched": 0, "affected": 0,
                        "note": "未匹配到文档，未做任何修改"}
            if n0 > _MAX_AFFECT:
                raise ValueError(f"匹配 {n0} 条文档超过上限 {_MAX_AFFECT}，未做修改，请缩小筛选范围")
            r = col.update_many(flt, {"$set": vals})
            return {"collection": table, "matched": r.matched_count, "affected": r.modified_count}
        return await asyncio.to_thread(_mongo_call, {"cfg": cfg, "database": db, "fn": run_upd})

    def run_del(client):
        col = client[db or "admin"][table]
        n0 = col.count_documents(flt)
        if n0 == 0:
            return {"collection": table, "affected": 0, "note": "未匹配到文档，未删除任何数据"}
        if n0 > _MAX_AFFECT:
            raise ValueError(f"匹配 {n0} 条文档超过上限 {_MAX_AFFECT}，未删除，请缩小筛选范围")
        r = col.delete_many(flt)
        return {"collection": table, "affected": r.deleted_count}
    return await asyncio.to_thread(_mongo_call, {"cfg": cfg, "database": db, "fn": run_del})
