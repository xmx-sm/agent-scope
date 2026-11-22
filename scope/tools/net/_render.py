

"""
crawl4ai 配置构建、服务端钳制与结果抽取（"高级网络请求"的无状态辅助）。

四组内容:
  1. 上限常量与日志器 —— 服务端硬钳制值，模型传参无法突破
  2. 配置构建：_valid_names / _build_config
     （未知参数报错并回 valid_params 名单供模型自纠，不静默吞）
  3. 原地钳制与改写：_apply_wait_for / _clamp_configs / _apply_extraction
     —— **三个纯副作用函数，不套信封**，坏入参 fail-fast 抛 ValueError
  4. 结果整形：_pick_output / _fail
"""


import inspect
import json
import logging
from typing import Any, Dict

from config import clamp_get as _clamp, get as _c, pick_str as _ps
from ._envelope import _err, _ok
from ._fs import _HOST_CTX, _check_write
# _HOST_CTX 由 configure_fs_policy() **原地 update** 而非重新绑定，
# 故模块级导入拿到同一 dict 对象，装配后注入的值在本模块同样可见（无需函数内 import）。

logger = logging.getLogger("async_crawl_tools")

# 服务端硬钳制上限（模型传参无法突破）
_PAGE_TIMEOUT_MAX_MS = 120_000      # page_timeout 单位毫秒（crawl4ai 原生语义）
_SEMAPHORE_MAX = 5
_RECYCLE_MAX = 50
_OUTPUT_MAX_LENGTH_DEFAULT = 20000
_BATCH_URLS_MAX = 20
_DEEP_PAGES_MAX = 30


def _valid_names(data: dict = None) -> Dict[str, Any]:
    """列出配置类 __init__ 接受的形参名（供模型自纠无效参数）。

    入参 (data): cls(type, 必填) crawl4ai 的配置类
    返回: {"code":200, "data": [参数名...], "message":"success"} 或 400 错误信封
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_valid_names")
    cls = data.get("cls")
    if cls is None:
        return _err("缺少 cls 字段（配置类）", "_valid_names")
    init = getattr(cls, "__init__", None)
    if init is None or not callable(init):
        return _err(f"{cls!r} 无可调用的 __init__", "_valid_names")
    try:
        ps = inspect.signature(init).parameters
    except (TypeError, ValueError) as e:
        return _err(f"无法取得 {getattr(cls, '__name__', cls)} 的签名：{e}", "_valid_names")
    return _ok([p for p in ps if p != "self"
               and ps[p].kind not in (inspect.Parameter.VAR_KEYWORD,
                                      inspect.Parameter.VAR_POSITIONAL)])


def _build_config(data: dict = None) -> Dict[str, Any]:
    """字典 → 官方配置对象；未知参数报错并回合法名单（模型自纠，不静默吞）。

    入参 (data):
        cls(type, 必填)     crawl4ai 配置类（CrawlerRunConfig / BrowserConfig）
        d(dict, 可选)       参数字典（透传官方字段名，铁律1：不发明同义字段）
        where(str, 可选)    错误位置标识，默认 "_build_config"

    返回:
        {"code":200, "data":{"config": <配置对象>}, "message":"success"}
        或 {"code":400, "data": 位置, "message": "错误：配置参数无效：…；valid_params=[...]"}
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_build_config")
    cls = data.get("cls")
    if cls is None:
        return _err("缺少 cls 字段（配置类）", "_build_config")
    d = data.get("d")
    if d is None:
        d = {}
    where = str(data.get("where") or "_build_config")
    if not isinstance(d, dict):
        return _err(f"d 必须是字典，收到 {type(d).__name__}", where)
    try:
        return _ok({"config": cls(**d)})
    except TypeError as e:
        vn = _valid_names({"cls": cls})
        names = vn["data"] if vn.get("code") == 200 else []
        return _err(f"配置参数无效：{e}；valid_params={names}", where)
    except Exception as e:
        return _err(f"构建配置失败：{type(e).__name__}: {e}", where)


def _apply_wait_for(data: dict = None) -> None:
    """wait_for 选择器 → 等效 js_code 轮询。**纯副作用（改 run_cfg.js_code），不套信封**。

    入参 (data):
        run_cfg(配置对象, 必填)  要被改写的 CrawlerRunConfig
        data(dict, 可选)         业务参数（读 wait_for，也看 run_config.wait_for）

    crawl4ai 0.9.4 的 run_config.wait_for 存在上游死锁缺陷（wait_for_target_elements
    恒为 None，selector 非空即走轮询分支 await None）——这里翻译成等效 js_code：
    页面加载后轮询等待选择器出现，最长等 min(page_timeout-5s, 15s)，超时不报错继续抓取。
    """
    if not isinstance(data, dict):
        raise ValueError("data 必须是字典对象")
    run_cfg = data.get("run_cfg")
    if run_cfg is None:
        raise ValueError("缺少 run_cfg 字段")
    biz = data.get("data")
    if biz is None:
        biz = {}
    if not isinstance(biz, dict):
        raise ValueError(f"data 必须是字典，收到 {type(biz).__name__}")
    sel = str(biz.get("wait_for", "") or "").strip() \
        or str((biz.get("run_config") or {}).get("wait_for", "") or "").strip()
    if not sel or run_cfg.js_code:
        return
    timeout_ms = int(run_cfg.page_timeout or 60_000)
    cap = max(int(_c("crawl.apply_wait_for.min_ms", 1_000)),
                min(timeout_ms - 5_000, _clamp("crawl.apply_wait_for.cap_ms", 15_000)))
    esc = json.dumps(sel)   # JSON 字符串转义，选择器含引号也安全
    run_cfg.js_code = (
        "() => { return new Promise(r => { const t = setInterval(() => {"
        f"if (document.querySelector({esc})) {{ clearInterval(t); r(); }} }}"
        ", 200); setTimeout(() => { clearInterval(t); r(); }, " + str(cap) + "); }); }")


def _clamp_configs(data: dict = None) -> None:
    """服务端硬钳制（铁律11）：超时/并发/回收上限、headed 许可、下载目录闸门。
    **纯副作用（原地改两个配置对象），不套信封**。

    入参 (data):
        run_cfg(配置对象, 必填)      CrawlerRunConfig
        br_cfg(配置对象, 可选)       BrowserConfig

    downloads_path 越界时抛 ValueError（由调用方 async_crawl/async_deep_crawl 捕获转 400）。
    """
    if not isinstance(data, dict):
        raise ValueError("data 必须是字典对象")
    run_cfg = data.get("run_cfg")
    if run_cfg is None:
        raise ValueError("缺少 run_cfg 字段")
    br_cfg = data.get("br_cfg")
    _pt_max = _clamp("crawl.page_timeout_max", _PAGE_TIMEOUT_MAX_MS)
    if run_cfg.page_timeout is None or run_cfg.page_timeout > _pt_max:
        run_cfg.page_timeout = _pt_max
    _sem_max = _clamp("crawl.semaphore_max", _SEMAPHORE_MAX)
    if run_cfg.semaphore_count is None or run_cfg.semaphore_count > _sem_max:
        run_cfg.semaphore_count = _sem_max
    if br_cfg is not None:
        if not _HOST_CTX.get("allow_headed") and br_cfg.headless is not True:
            br_cfg.headless = True
        _rc_max = _clamp("crawl.recycle_max", _RECYCLE_MAX)
        if br_cfg.max_pages_before_recycle is None or \
                br_cfg.max_pages_before_recycle > _rc_max:
            br_cfg.max_pages_before_recycle = _rc_max
        if getattr(br_cfg, "downloads_path", None):
            cw = _check_write({"path": str(br_cfg.downloads_path)})
            if cw.get("code") != 200:
                raise ValueError(str(cw.get("message")))
            if not cw["data"]["allowed"]:
                raise ValueError(f"downloads_path 被拒：{cw['data']['reason']}")


def _apply_extraction(data: dict = None) -> None:
    """结构化抽取策略装配。**纯副作用（改 run_cfg 的两个字段），不套信封**。

    入参 (data):
        run_cfg(配置对象, 必填)  CrawlerRunConfig
        data(dict, 可选)         业务参数（读 extraction: {type, schema|pattern/custom}）

    0.9.4 实证：清洗器按 word_count_threshold 删"词数不足且无子元素"
    的节点（h1/短标题全被剥），extraction 时强制阈值归零保住标签，否则 schema 必空。

    extraction.type 非法时抛 ValueError（由调用方捕获转 400）。
    """
    if not isinstance(data, dict):
        raise ValueError("data 必须是字典对象")
    run_cfg = data.get("run_cfg")
    if run_cfg is None:
        raise ValueError("缺少 run_cfg 字段")
    biz = data.get("data")
    if biz is None:
        biz = {}
    if not isinstance(biz, dict):
        raise ValueError(f"data 必须是字典，收到 {type(biz).__name__}")
    if not biz.get("extraction"):
        return
    extraction = biz["extraction"]
    if not isinstance(extraction, dict):
        raise ValueError(f"extraction 必须是字典，收到 {type(extraction).__name__}")
    import crawl4ai
    etype = _ps(extraction.get("type"), "crawl.extraction.type", "css").lower()
    if etype == "css":
        run_cfg.extraction_strategy = crawl4ai.JsonCssExtractionStrategy(
            extraction.get("schema"))
    elif etype == "xpath":
        run_cfg.extraction_strategy = crawl4ai.JsonXPathExtractionStrategy(
            extraction.get("schema"))
    elif etype == "regex":
        run_cfg.extraction_strategy = crawl4ai.RegexExtractionStrategy(
            pattern=extraction.get("pattern"), custom=extraction.get("custom"))
    else:
        raise ValueError(f"不支持的 extraction.type: {etype}（css/xpath/regex）")
    run_cfg.word_count_threshold = 0


def _pick_output(data: dict = None) -> Dict[str, Any]:
    """按 output_format 选取抓取输出并截断。

    入参 (data):
        res(响应对象, 必填)         crawl4ai 的 CrawledData
        output_format(str, 可选)    markdown（默认）/ html / links
        max_length(int, 可选)       正文字符上限，缺省 _OUTPUT_MAX_LENGTH_DEFAULT，0=不限

    返回:
        {"code":200, "data": {"url","status_code","success", 视格式
                              "content"/"links"/"extracted"/"screenshot_b64","truncated"},
         "message":"success"}
        或 {"code":400, "data": 位置, "message": "错误：<原因>"}
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_pick_output")
    res = data.get("res")
    if res is None:
        return _err("缺少 res 字段（抓取响应对象）", "_pick_output")
    output_format = str(data.get("output_format") or _c("crawl.output_format", "markdown")).strip().lower()
    if output_format not in ("markdown", "html", "links"):
        return _err(f"output_format 仅支持 markdown / html / links，收到 {output_format!r}",
                    "_pick_output")
    raw_max = data.get("max_length")
    if raw_max in (None, ""):
        raw_max = _c("crawl.output_max_length_default", _OUTPUT_MAX_LENGTH_DEFAULT)
    if isinstance(raw_max, (dict, list, tuple, set)):
        return _err(f"max_length 必须是整数，收到 {type(raw_max).__name__}", "_pick_output")
    try:
        max_length = int(raw_max)
    except (TypeError, ValueError):
        return _err("max_length 必须是整数", "_pick_output")
    if max_length < 0:
        max_length = 0

    out: Dict[str, Any] = {"url": getattr(res, "url", None),
                           "status_code": getattr(res, "status_code", None),
                           "success": bool(getattr(res, "success", False))}
    if output_format == "links":
        links = getattr(res, "links", None) or {}
        _ll = _clamp("crawl.links_limit", 200)
        trim = lambda vs: [{"href": v.get("href"), "text": (v.get("text") or "").strip()}
                           for v in (vs or [])][:_ll]
        return _ok({**out, "links": {"internal": trim(links.get("internal")),
                                     "external": trim(links.get("external"))}})
    if output_format == "html":
        text = getattr(res, "html", None) or ""
    else:  # markdown（默认；PDF run_config.pdf=true 时文本同样落在此字段）
        md = getattr(res, "markdown", None)
        if isinstance(md, dict):
            text = md.get("raw_markdown") or md.get("markdown") or ""
        else:
            text = getattr(md, "raw_markdown", None) or str(md or "")
    extracted = getattr(res, "extracted_content", None)
    if extracted is not None:
        try:
            out["extracted"] = json.loads(extracted)
        except (TypeError, ValueError):
            out["extracted"] = extracted
    truncated = False
    if max_length > 0 and len(text) > max_length:
        text, truncated = text[:max_length], True
    out.update({"content": text, "truncated": truncated})
    if getattr(res, "screenshot", None):
        out["screenshot_b64"] = res.screenshot
    return _ok(out)


def _fail(data: dict = None) -> Dict[str, Any]:
    """抓取失败的 500 信封（含 0.9.4 结构启发式误杀的自救指引）。

    入参 (data):
        where(str, 可选)   错误位置标识
        res(响应对象, 必填) crawl4ai 的 CrawledData

    返回: {"code":500, "data": 位置, "message": 失败原因（附误判说明）}

    500 不带「错误：」前缀（与原实现及各域约定一致：500 是运行时失败描述）。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_fail")
    res = data.get("res")
    if res is None:
        return _err("缺少 res 字段（抓取响应对象）", "_fail")
    where = str(data.get("where") or "_fail")
    msg = f"抓取失败：{getattr(res, 'error_message', None) or '未知错误'}"
    if "anti-bot" in msg or "Structural" in msg:
        msg += ("（0.9.4 的结构启发式会把「正文少+脚本多」的正常小页面误判为反爬空壳；"
                "若确认目标可信，可在 run_config 里加 excluded_tags=[] 并换 output_format="
                "\"html\" 重试，或增大 wait_for/delay 让内容充分渲染）")
    return _err(msg, where, code=500)
