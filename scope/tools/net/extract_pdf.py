

"""function="extract_pdf" — PDF 结构化抽取（读前过宿主文件闸门 _check_read）。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。

0.9.4 实证：浏览器路径不可用——file:// 走 utf-8 解码必炸、http(s) PDF 触发
"Download is starting" 导航失败。改走官方 PDFContentScrapingStrategy.scrap()
（内部 requests 下载 + pdfminer 解析，不经浏览器）；同步重 IO 按铁律8 to_thread。
"""


import asyncio
import re
from typing import Any, Dict

from ._envelope import _err, _ok
from ._fs import _check_read
from config import get as _c
from ._render import logger


async def async_extract_pdf(data: dict = None) -> Dict[str, Any]:
    """
    PDF 转文本（本地 pdf_path 或在线 url 二选一）。

    入参 (data):
        pdf_path(str, 条件)   本地 PDF 路径（**过读闸门** check_read）
        url(str, 条件)        在线 PDF 地址
                              —— 两者至少填一个；都给时 pdf_path 优先
        max_length(int, 可选) 文本字符上限，缺省 20000，0=不限

    返回:
        {"code":200, "data": {"url": 实际目标, "pages": 页数, "content": 文本,
                              "truncated": bool}, "message":"success"}
        {"code":400, ...} 参数缺失、路径被闸门拒绝
        {"code":500, ...} crawl4ai/bs4 未安装或解析失败

    依赖 crawl4ai（PDFContentScrapingStrategy）与 beautifulsoup4（lxml 解析）。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "async_extract_pdf")
    pdf_path = str(data.get("pdf_path", "") or "").strip()
    url = str(data.get("url", "") or "").strip()
    if not pdf_path and not url:
        return _err("pdf_path 与 url 至少填一个", "async_extract_pdf")
    if pdf_path:
        cr = _check_read({"path": pdf_path})
        if cr.get("code") != 200:
            return cr
        if not cr["data"]["allowed"]:
            return _err(f"读取路径被拒：{cr['data']['reason']}", "async_extract_pdf")
    target = pdf_path or url
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return _err("未安装 beautifulsoup4（pip install beautifulsoup4）", "async_extract_pdf")
    try:
        from crawl4ai import PDFContentScrapingStrategy
    except ImportError:
        return _err("crawl4ai 未安装，无法解析 PDF", "async_extract_pdf")
    raw_max = data.get("max_length")
    if raw_max in (None, ""):
        raw_max = _c("crawl.output_max_length_default", 20000)
    if isinstance(raw_max, (dict, list, tuple, set)):
        return _err(f"max_length 必须是整数，收到 {type(raw_max).__name__}", "async_extract_pdf")
    try:
        max_length = int(raw_max)
    except (TypeError, ValueError):
        return _err("max_length 必须是整数", "async_extract_pdf")
    try:
        strategy = PDFContentScrapingStrategy()
        result = await asyncio.to_thread(strategy.scrap, target, "")
        cleaned = getattr(result, "cleaned_html", "") or ""
        soup = BeautifulSoup(cleaned, "lxml")
        pages = len(soup.select(".pdf-page"))
        text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True))
        truncated = False
        if max_length > 0 and len(text) > max_length:
            text, truncated = text[:max_length], True
        return _ok({"url": target, "pages": pages, "content": text, "truncated": truncated})
    except Exception as ex:
        logger.exception("extract_pdf failed")
        return _err(f"处理失败，原因：{ex}", "async_extract_pdf", code=500)
