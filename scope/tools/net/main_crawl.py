

"""
crawl 工具统一入口与 function 路由（crawl4ai 浏览器抓取）。

原 async_crawl_tools.py 拆分而来并独立成 crawl 文件夹：本文件只保留调度，
每个功能一个模块。新增功能：写一个 <function>.py，并在本文件路由里加一个 if function == "..." 分支。

平台装配时须调用 configure_fs_policy() 注入文件闸门（见 _helper.py）。

模块布局:
    main_crawl.py   本文件，async_crawl_tools 入口与路由
    _helper.py      无状态辅助：上限常量、错误包装、配置构建与钳制、输出抽取、宿主文件闸门
    _crawler.py     AsyncWebCrawler 进程级单例与复用/回收（有状态，故独立）
    crawl.py        function="crawl"         单页抓取
    crawl_many.py   function="crawl_many"    批量抓取
    deep_crawl.py   function="deep_crawl"    站内深爬
    screenshot.py   function="screenshot"    页面截图
    extract_pdf.py  function="extract_pdf"   PDF 抽取
"""

from typing import Any, Dict

from ._envelope import _err
from ._fs import configure_fs_policy
from .crawl import async_crawl
from .crawl_many import async_crawl_many
from .deep_crawl import async_deep_crawl
from .extract_pdf import async_extract_pdf
from .screenshot import async_screenshot



# ========== 分发入口 ==========
async def async_crawl_tools(data: dict) -> Dict[str, Any]:
    """
    网络访问 pro 工具统一入口（异步，浏览器渲染抓取）。data["function"] 决定执行哪个功能，
    其余字段为该功能的业务参数。适合 JS 动态渲染页面；纯静态页/JSON 接口用
    async_req_tools.http_request 更快。

    参数 (data 字典):
        data: {"function": "crawl"|"crawl_many"|"deep_crawl"|"screenshot"|"extract_pdf",
               ...业务参数见下方各功能说明}

    支持的功能与业务参数:
        ① function="crawl" — 单页抓取（JS 渲染后）
            业务参数: url(str,必填)
                     run_config(dict,可选) → CrawlerRunConfig 官方参数透传，常用：
                         css_selector/word_count_threshold/excluded_tags/screenshot/pdf/
                         js_code/method/user_agent/proxy/storage_state/cookies；
                         wait_for(str) 顶层或 run_config 内均可——等 CSS 选择器出现
                         （内部译成轮询 js_code，规避 crawl4ai 0.9.4 wait_for 死锁缺陷）
                     browser_config(dict,可选) → BrowserConfig 官方参数透传，常用：
                         headless(默认强制true)/proxy/viewport/user_agent/headers/
                         cookies/enable_stealth/avoid_ads/downloads_path
                     extraction(dict,可选) {"type":"css|xpath|regex","schema":{...},
                         "pattern":..., "custom":[...]}——结构化抽取，结果在 data.extracted
                     output_format(str,可选) "markdown"(默认)/"html"/"links"
                     max_length(int,可选) 正文最大字符数，默认 20000，<=0 不截断
            返回: {"code":200,"data":{url,status_code,content|links,extracted?,
                   screenshot_b64?,truncated},"message":"success"}
        ② function="crawl_many" — 多 URL 批量（单次≤20，顺序执行）
            业务参数: urls(list[str],必填)，其余同 crawl
            返回: data={total,ok,results:[每URL结果]}
        ③ function="deep_crawl" — 站内 BFS 多页爬取
            业务参数: url(str,必填起点)、max_depth(int,默认2)、total_limit(int,默认10,≤30)、
                     concurrent_limit(int,默认4,≤5)、accept_url_patterns/
                     ignore_url_patterns(list[glob],可选)
        ④ function="screenshot" — 整页/元素截图存盘
            业务参数: url(str,必填)、save_path(str,必填，受文件访问边界约束)、
                     full_page(bool,默认true)、css_selector/wait_for(可选)
            返回: data={save_path,url}
        ⑤ function="extract_pdf" — PDF 转文本
            业务参数: pdf_path(str,本地文件，与 url 二选一) 或 url(str,在线PDF)
                     run_config/output_format 同 crawl（自动开 pdf=true）

    调用示例:
        async_crawl_tools({"function":"crawl","url":"https://spa-example.com",
                           "run_config":{"wait_for":".loaded"}})
        async_crawl_tools({"function":"crawl","url":"https://example.com",
                           "extraction":{"type":"css","schema":{
                             "name":"articles","base":"article",
                             "elements":[{"name":"title","selector":"h1"}]}}})
        async_crawl_tools({"function":"deep_crawl","url":"https://site.com",
                           "max_depth":2,"accept_url_patterns":["site.com/blog/*"]})
        async_crawl_tools({"function":"screenshot","url":"https://example.com",
                           "save_path":"/workdir/shot.png"})
        async_crawl_tools({"function":"extract_pdf","pdf_path":"/tmp/report.pdf"})

    返回:
        {"code": 200, "data": ..., "message": "success"}
        或 {"code": 400/500, "data": 文件位置, "message": 错误描述}
        run_config/browser_config 未知参数 → code 400 且 message 附 valid_params 名单
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "async_crawl_tools")
    raw_fn = data.get("function", "")
    if isinstance(raw_fn, (dict, list, tuple, set)):
        return _err(f"function 必须是字符串，收到 {type(raw_fn).__name__}", "async_crawl_tools")
    function = str(raw_fn or "").strip()
    if not function:
        return _err("data 中缺少 function 字段", "async_crawl_tools")
    if function == "crawl":
        return await async_crawl(data)
    if function == "crawl_many":
        return await async_crawl_many(data)
    if function == "deep_crawl":
        return await async_deep_crawl(data)
    if function == "screenshot":
        return await async_screenshot(data)
    if function == "extract_pdf":
        return await async_extract_pdf(data)
    return _err(f"暂不支持的 function: {function}，"
                f"支持: crawl / crawl_many / deep_crawl / screenshot / extract_pdf", "async_crawl_tools", prefix=False)



__all__ = ["async_crawl_tools", "configure_fs_policy"]
