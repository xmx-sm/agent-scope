

"""function="crawl" — 单页抓取（JS 渲染后，动态页面/结构化抽取）。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。

crawl4ai 是可选依赖：原实现 `import crawl4ai` 在函数体首行，未安装时裸抛
ModuleNotFoundError；现包进 try 返回 500 信封，使本域错误形状统一（调用方只判 code）。
"""


from typing import Any, Dict

from ._crawler import _get_crawler, _reset_crawler
from ._envelope import _err, _ok
from config import pick_str as _ps
from ._render import _apply_extraction, _apply_wait_for, _build_config, _clamp_configs, _fail, _pick_output, logger


async def async_crawl(data: dict = None) -> Dict[str, Any]:
    """
    单页抓取（JS 渲染后）。

    入参 (data):
        url(str, 必填)                目标地址
        run_config(dict, 可选)        透传 crawl4ai CrawlerRunConfig 字段
                                      （wait_for/excluded_tags/css_selector/delay 等）
        browser_config(dict, 可选)    透传 crawl4ai BrowserConfig 字段
        output_format(str, 可选)      markdown（默认）/ html / links
        max_length(int, 可选)         正文字符上限，缺省 20000，0=不限
        extraction(dict, 可选)        结构化抽取 {type: css|xpath|regex, schema|pattern}

    返回:
        {"code":200, "data": <_pick_output 的产物>, "message":"success"}
        {"code":400, ...} 参数/配置无效（附 valid_params 供自纠）
        {"code":500, ...} 抓取失败或 crawl4ai 未安装/浏览器启动失败

    0.9.4 的两处上游缺陷已在此层规避:
        - wait_for 死锁 → _apply_wait_for 翻译成 js_code 轮询
        - 结构启发式误杀短正文页 → 下方 rescue 分支
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "async_crawl")
    try:
        import crawl4ai
    except ImportError:
        return _err("未安装 crawl4ai（pip install crawl4ai），"
                                   "该工具为可选依赖，其余网络功能不受影响", "async_crawl")
    url = str(data.get("url", "") or "").strip()
    if not url:
        return _err("data 中缺少 url 字段", "async_crawl")
    bc = _build_config({"cls": crawl4ai.CrawlerRunConfig, "d": data.get("run_config"),
                        "where": "async_crawl"})
    if bc.get("code") != 200:
        return bc
    run_cfg = bc["data"]["config"]
    bc2 = _build_config({"cls": crawl4ai.BrowserConfig, "d": data.get("browser_config"),
                         "where": "async_crawl"})
    if bc2.get("code") != 200:
        return bc2
    br_cfg = bc2["data"]["config"]
    try:
        _clamp_configs({"run_cfg": run_cfg, "br_cfg": br_cfg})
        _apply_wait_for({"run_cfg": run_cfg, "data": data})
        _apply_extraction({"run_cfg": run_cfg, "data": data})
    except ValueError as ex:
        return _err(f"{ex}", "async_crawl")
    try:
        gc = await _get_crawler({"browser_cfg": br_cfg})
        if gc.get("code") != 200:
            return gc
        crawler = gc["data"]
        res = await crawler.arun(url, config=run_cfg)
        if not res.success and "anti-bot" in (res.error_message or "") \
                and not run_cfg.css_selector:
            # 0.9.4 结构启发式误杀短正文页（实测 httpbin.org/html 整页被剥成空壳）：
            # css_selector=body 走直通路径跳过清洗，自动救一次
            rescue_cfg = crawl4ai.CrawlerRunConfig(**{
                **{k: v for k, v in run_cfg.__dict__.items() if v is not None},
                "css_selector": "body"})
            res2 = await crawler.arun(url, config=rescue_cfg)
            if res2.success:
                res = res2
                res._c4a_rescued = True
        if not res.success:
            return _fail({"where": "async_crawl", "res": res})
        po = _pick_output({"res": res,
                           "output_format": _ps(data.get("output_format"), "crawl.output_format", "markdown"),
                           "max_length": data.get("max_length")})
        if po.get("code") != 200:
            return po
        out = po["data"]
        if getattr(res, "_c4a_rescued", False):
            out["note"] = "页面正文过短触发反爬启发式误判，已按 body 直通重抓"
        return _ok(out)
    except Exception as ex:
        await _reset_crawler()   # 自愈：下次调用重建浏览器
        logger.exception("crawl failed, browser reset")
        return _err(f"处理失败，原因：{ex}", "async_crawl", code=500)
