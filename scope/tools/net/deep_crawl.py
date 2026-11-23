

"""function="deep_crawl" — 站内 BFS 多页爬取（受页数上限与并发信号量钳制）。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。
"""


from typing import Any, Dict

from ._crawler import _get_crawler, _reset_crawler
from ._envelope import _err, _ok
from common.net_guard import check_url as _check_url
from config import clamp_get as _clamp, pick_int as _pi, pick_str as _ps
from ._render import _DEEP_PAGES_MAX, _SEMAPHORE_MAX, _apply_wait_for, _build_config, _clamp_configs, _pick_output, logger


async def async_deep_crawl(data: dict = None) -> Dict[str, Any]:
    """
    站内 BFS 多页爬取。

    入参 (data):
        url(str, 必填)                 起点地址
        max_depth(int, 可选)           爬取深度，默认 2
        total_limit(int, 可选)         总页数上限，默认 10，钳到 _DEEP_PAGES_MAX=30
        concurrent_limit(int, 可选)    并发数，默认 4，钳到 _SEMAPHORE_MAX=5
        accept_url_patterns(list, 可选) 只爬匹配的 URL
        ignore_url_patterns(list, 可选) 跳过匹配的 URL
        run_config / browser_config / output_format / max_length 同 async_crawl

    返回:
        {"code":200, "data": {"total":N, "results":[各页产物]}, "message":"success"}
        或 {"code":400/500, ...}

    0.9.4 的 deep_crawl_strategy 挂在 config 上时，arun() 被 DeepCrawlDecorator
    包装为返回 List[CrawlResult]（不是单结果），故下方按 list 归一。
    失败的页（success=False）不进 results，只计成功页；total 是实际返回页数。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "async_deep_crawl")
    url = str(data.get("url", "") or "").strip()
    if not url:
        return _err("data 中缺少 url 字段", "async_deep_crawl")
    allowed, reason = await _check_url(url)
    if not allowed:
        return _err(f"URL 被拒绝：{reason}", "async_deep_crawl")
    try:
        import crawl4ai
    except ImportError:
        return _err("未安装 crawl4ai（pip install crawl4ai），"
                                        "该工具为可选依赖，其余网络功能不受影响", "async_deep_crawl")
    for k in ("max_depth", "total_limit", "concurrent_limit", "max_length"):
        v = data.get(k)
        if v is not None and isinstance(v, (dict, list, tuple, set)):
            return _err(f"{k} 必须是整数，收到 {type(v).__name__}", "async_deep_crawl")
    try:
        max_depth = int(_pi(data.get("max_depth"), "crawl.deep_crawl.max_depth", 2))
        total_limit = min(int(_pi(data.get("total_limit"), "crawl.deep_crawl.total_limit", 10)),
                          _clamp("crawl.deep_pages_max", _DEEP_PAGES_MAX))
        concurrency = min(int(_pi(data.get("concurrent_limit"), "crawl.deep_crawl.concurrent_limit", 4)),
                          _clamp("crawl.semaphore_max", _SEMAPHORE_MAX))
    except (TypeError, ValueError):
        return _err("max_depth/total_limit/concurrent_limit 必须是整数", "async_deep_crawl")
    bc = _build_config({"cls": crawl4ai.CrawlerRunConfig, "d": data.get("run_config"),
                        "where": "async_deep_crawl"})
    if bc.get("code") != 200:
        return bc
    run_cfg = bc["data"]["config"]
    bc2 = _build_config({"cls": crawl4ai.BrowserConfig, "d": data.get("browser_config"),
                         "where": "async_deep_crawl"})
    if bc2.get("code") != 200:
        return bc2
    br_cfg = bc2["data"]["config"]
    try:
        _clamp_configs({"run_cfg": run_cfg, "br_cfg": br_cfg})
        _apply_wait_for({"run_cfg": run_cfg, "data": data})
    except ValueError as ex:
        return _err(f"{ex}", "async_deep_crawl")
    run_cfg.semaphore_count = concurrency
    filters = []
    accept = data.get("accept_url_patterns") or []
    ignore = data.get("ignore_url_patterns") or []
    if not isinstance(accept, (list, tuple)):
        return _err(f"accept_url_patterns 必须是列表，收到 {type(accept).__name__}", "async_deep_crawl")
    if not isinstance(ignore, (list, tuple)):
        return _err(f"ignore_url_patterns 必须是列表，收到 {type(ignore).__name__}", "async_deep_crawl")
    if accept:
        filters.append(crawl4ai.URLPatternFilter(patterns=list(accept)))
    if ignore:
        filters.append(crawl4ai.URLPatternFilter(patterns=list(ignore), reverse=True))
    run_cfg.deep_crawl_strategy = crawl4ai.BFSDeepCrawlStrategy(
        max_depth=max_depth,
        filter_chain=crawl4ai.FilterChain(filters=filters),
        max_pages=total_limit,
        # 安全边界：只爬起点同域页面，避免被站外链接带去访问内网/元数据地址。
        include_external=False)
    try:
        gc = await _get_crawler({"browser_cfg": br_cfg})
        if gc.get("code") != 200:
            return gc
        crawler = gc["data"]
        # deep_crawl_strategy 挂在 config 上时，0.9.4 的 arun() 被 DeepCrawlDecorator
        # 包装为返回 List[CrawlResult]（不是单结果）
        ress = await crawler.arun(url, config=run_cfg)
        items = []
        for res in (ress if isinstance(ress, list) else [ress]):
            if res.success:
                po = _pick_output({"res": res,
                                   "output_format": _ps(data.get("output_format"), "crawl.output_format", "markdown"),
                                   "max_length": data.get("max_length")})
                if po.get("code") != 200:
                    return po
                items.append(po["data"])
        return _ok({"total": len(items), "results": items})
    except Exception as ex:
        await _reset_crawler()
        logger.exception("deep_crawl failed, browser reset")
        return _err(f"处理失败，原因：{ex}", "async_deep_crawl", code=500)
