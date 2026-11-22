

"""function="crawl_many" — 批量抓取多个 URL（复用 async_crawl，受批上限钳制）。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。

单个 URL 失败不影响其余：失败的条目记 {url, success:false, error}。
"""


from typing import Any, Dict

from ._envelope import _err, _ok
from ._render import _BATCH_URLS_MAX
from .crawl import async_crawl


async def async_crawl_many(data: dict = None) -> Dict[str, Any]:
    """
    多 URL 批量抓取（单次 ≤ _BATCH_URLS_MAX=20）。

    入参 (data):
        urls(list[str], 必填)   目标地址列表，非空且不超上限
        其余字段同 async_crawl（run_config/browser_config/output_format/max_length）

    返回:
        {"code":200, "data": {"total":N, "ok":N, "results":[各页产物或失败记录]},
         "message":"success"}
        或 {"code":400, ...} urls 非法

    注意：整批入参非法（urls 缺失/空/超上限）才返回 400；
    批内单页失败只体现在该条 result 里，整体仍返回 200。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "async_crawl_many")
    urls = data.get("urls")
    if not isinstance(urls, list) or not urls:
        return _err("urls 必须是非空列表", "async_crawl_many")
    if len(urls) > _BATCH_URLS_MAX:
        return _err(f"单次最多 {_BATCH_URLS_MAX} 个 URL", "async_crawl_many")
    results = []
    for u in urls:
        r = await async_crawl({**data, "url": str(u)})
        if r.get("code") == 200:
            results.append(r["data"])
        else:
            results.append({"url": str(u), "success": False, "error": r.get("message")})
    ok = sum(1 for x in results if x.get("success"))
    return _ok({"total": len(results), "ok": ok, "results": results})
