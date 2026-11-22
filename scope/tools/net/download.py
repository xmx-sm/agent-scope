

"""
function="download" — 文件下载（大小上限、进度上报可控）。
"""


import httpx
import os
from typing import Dict, Any

from ._client import get_http_client, get_timeout
from ._envelope import _err, _ok
from ._fs import _check_write



async def async_req_download(data: dict) -> Dict[str, Any]:
    """
    流式下载文件到本地（异步，httpx stream 模式）。适合大文件：边下载边产出进度，
    无需等全部下载完即可实时看到中间进度；结束时返回保存路径与大小。

    参数 (data 字典):
        data: {"url": 下载地址(必填)，
               "save_path": 本地保存路径，绝对路径(必填，父目录不存在自动创建)，
               "timeout": 请求/读取超时秒数(可选,默认30)，
               "max_size": 最大下载字节数(可选,默认0不限制；超出即停止)，
               "report_every": 每下载多少字节汇报一次进度(可选,默认1048576=1MB)}

    返回（流式）:
        边下载边产出进度文本（如 "已下载 5MB"）；
        最后产出 {"code":200,"data":{"save_path","size","status_code"},"message":"下载完成"}
        或 {"code":400/500,"data":文件位置,"message":"错误描述"}
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "download")
    url = str(data.get("url", "") or "").strip()
    if not url:
        return _err("data 中缺少 url 字段", "download")
    save_path = str(data.get("save_path", "") or "").strip()
    if not save_path:
        return _err("data 中缺少 save_path 字段", "download")
    # ⚠️ 文件闸门（合并 crawl 后补上）：download 原先直接 open(save_path,"wb") 落盘，
    #    而同域的 screenshot 却过 _check_write —— 同一能力两种命运，
    #    平台注入的租户约束对 download 完全失效（可写到 uploads 根之外）。
    #    闸门必须在 makedirs 之前：建目录本身也是写操作。
    gw = _check_write({"path": save_path})
    if gw.get("code") != 200:
        return gw
    if not gw["data"]["allowed"]:
        return _err(f"保存路径被拒：{gw['data']['reason']}", "download")
    timeout_r = get_timeout({"data": data, "func_name": "download", "default": 30})
    if timeout_r.get("code") != 200:
        return timeout_r
    try:
        max_size = int(data.get("max_size", 0) or 0)
        if max_size < 0:
            max_size = 0
        report_every = int(data.get("report_every", 1048576) or 1048576)
        if report_every <= 0:
            report_every = 1048576
    except (TypeError, ValueError):
        return _err("max_size / report_every 必须是整数", "download")
    # verify 交由 get_http_client 统一判定：无法识别的值报 400，不再静默降级为禁用 TLS 校验
    cr = get_http_client({"verify": data.get("verify", True)})
    if cr.get("code") != 200:
        return cr                      # 外层是普通 async 函数：校验失败直接返回信封，
    client = cr["data"]                # 成功才 return stream()（异步生成器）
    try:
        os.makedirs(os.path.dirname(os.path.abspath(save_path)) or ".", exist_ok=True)
    except OSError as e:
        return _err(f"无法创建保存目录 - {e}", "download")

    async def stream():
        try:
            downloaded = 0
            size = 0
            last_report = 0
            status_code = None
            # 共享客户端 stream 模式：逐块接收，边下边写边汇报进度
            async with client.stream("GET", url, timeout=timeout_r["data"]["value"]) as resp:
                resp.raise_for_status()
                status_code = resp.status_code
                # 总大小：服务端可能不返回 content-length，此时 total=0 表示未知
                total = int(resp.headers.get("content-length", 0) or 0)
                with open(save_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if max_size > 0 and downloaded >= max_size:
                            break
                        if report_every and downloaded - last_report >= report_every:
                            last_report = downloaded
                            progress = f"已下载 {downloaded / 1048576:.1f}MB"
                            if total:
                                progress += f" / {total / 1048576:.1f}MB ({downloaded * 100 // total}%)"
                            yield progress
            size = downloaded
            # 最终汇总：路径 + 实际大小 + 状态码
            yield _ok({"save_path": save_path, "size": size, "status_code": status_code},
                      "下载完成")
        except httpx.TimeoutException:
            yield _err(f"下载超时：{url}", "download", code=500)
        except httpx.HTTPStatusError as e:
            yield _err(f"HTTP错误：{e}", "download", code=500)
        except Exception as e:
            yield _err(f"下载失败：{e}", "download", code=500)

    return stream()
