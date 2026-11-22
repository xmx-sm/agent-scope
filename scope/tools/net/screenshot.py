

"""function="screenshot" — 页面截图落盘（写前过宿主文件闸门 _check_write）。

入参统一为 data 字典，返回统一为 {"code", "data", "message"} 信封。

实现要点：复用 async_crawl 拿 screenshot_b64（max_length=1 只为省正文），
再 base64 解码写盘。截图数据来自 crawl4ai 的 screenshot 参数。
"""


import base64
import os
from typing import Any, Dict

from ._envelope import _err, _ok
from ._fs import _check_write
from config import pick_int as _pi
from .crawl import async_crawl


async def async_screenshot(data: dict = None) -> Dict[str, Any]:
    """
    整页/元素截图存盘。

    入参 (data):
        url(str, 必填)                目标地址
        save_path(str, 必填)          本地保存路径（**过文件闸门**：平台注入的 check_write
                                      或独立模式的 cwd 子树兜底）
        css_selector(str, 可选)       只截指定元素
        full_page(bool, 可选)         默认整页；显式 False 时转 force_viewport_screenshot
        wait_ms(int, 可选)            截图前等待毫秒数，默认 1000
                                      （crawl4ai 的 delay_before_return_html 单位是**秒**，
                                        此处传毫秒并除以 1000 换算）
        run_config(dict, 可选)        透传字段，与本层生成的 rc 合并（本层优先）

    返回:
        {"code":200, "data": {"save_path": str, "url": str}, "message":"截图已保存"}
        {"code":400, ...} url/save_path 缺失、路径被闸门拒绝
        {"code":500, ...} 抓取成功但无截图数据、或写盘失败
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "async_screenshot")
    url = str(data.get("url", "") or "").strip()
    save_path = str(data.get("save_path", "") or "").strip()
    if not url or not save_path:
        return _err("url 与 save_path 均必填", "async_screenshot")
    cw = _check_write({"path": save_path})
    if cw.get("code") != 200:
        return cw
    if not cw["data"]["allowed"]:
        return _err(f"保存路径被拒：{cw['data']['reason']}", "async_screenshot")
    rc: Dict[str, Any] = {"screenshot": True}
    raw_wait = _pi(data.get("wait_ms"), "crawl.screenshot.wait_ms", 1000)
    if raw_wait in (None, ""):
        raw_wait = 1000
    if isinstance(raw_wait, (dict, list, tuple, set)):
        return _err(f"wait_ms 必须是整数，收到 {type(raw_wait).__name__}", "async_screenshot")
    try:
        wait_ms = int(raw_wait)
    except (TypeError, ValueError):
        return _err("wait_ms 必须是整数", "async_screenshot")
    if wait_ms > 0:
        # crawl4ai 的 delay_before_return_html 是秒（内部 asyncio.sleep），传毫秒会睡千倍时长
        rc["delay_before_return_html"] = wait_ms / 1000.0
    if data.get("full_page") is False:
        rc["force_viewport_screenshot"] = True
    if data.get("css_selector"):
        rc["css_selector"] = data["css_selector"]
    raw_rc = data.get("run_config")
    if raw_rc is not None and not isinstance(raw_rc, dict):
        return _err(f"run_config 必须是字典，收到 {type(raw_rc).__name__}", "async_screenshot")
    merged = {**(raw_rc or {}), **rc}
    r = await async_crawl({**data, "url": url, "run_config": merged,
                           "output_format": "markdown", "max_length": 1})
    if r.get("code") != 200:
        return r
    b64 = (r.get("data") or {}).get("screenshot_b64")
    if not b64:
        return _err("抓取成功但未返回截图数据", "async_screenshot", code=500)
    try:
        parent = os.path.dirname(os.path.abspath(save_path))
        os.makedirs(parent, exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(b64))
        return _ok({"save_path": save_path, "url": url}, "截图已保存")
    except Exception as ex:
        return _err(f"保存失败，原因：{ex}", "async_screenshot", code=500)
