

"""
IMAP / SMTP 连接生命周期。

入参统一为 data 字典。

`_abandon_imap` / `_wait_imap_hello` 是**纯副作用函数**（只改连接对象状态、只抛异常，
无数据可返回），故不套信封——保持原返回 None 与 raise 语义。

`async_open_imap` / `async_open_smtp` 返回活连接对象，套信封：
    {"code":200, "data": <连接对象>, "message":"success"}
原实现建连失败一律 raise（RuntimeError / 最后一个真实异常），由调用方 try/except 转 500；
现改为返回 400/500 信封，调用方 `if r.get("code") != 200: return r` 显式转发。

⚠️ 安全不变量（勿在重构中松动）:
    - SMTP: 非 465 端口若 STARTTLS 升级不成，**拒绝连接**——否则授权码以明文过网络
    - IMAP: 143 端口握手失败给出"本平台不以明文提交授权码，请改用 993/SSL"的明确指引
    - 两条失败路径都必须先关掉半开连接（_abandon_imap / client.close），防 fd 泄漏
"""


import asyncio
from typing import Any, Dict

import aioimaplib
from aiosmtplib import SMTP

from ._helper import _err, _ok, imap_connect_error, imap_ssl_contexts


async def _abandon_imap(data: dict = None) -> None:
    """丢弃半开 IMAP 连接：握手失败的 aioimaplib 实例仍挂着 create_connection 任务和 socket。

    入参 (data): conn(aioimaplib 连接, 可选)

    **不套信封**（纯副作用）。任何异常都吞掉——清理失败不该掩盖原始握手错误。
    """
    if not isinstance(data, dict):
        return None
    conn = data.get("conn")
    if conn is None:
        return None
    try:
        transport = getattr(conn.protocol, "transport", None)
        if transport is not None:
            transport.close()
    except BaseException:
        pass
    try:
        conn._client_task.cancel()
    except BaseException:
        pass


async def _wait_imap_hello(data: dict = None) -> None:
    """等服务端 greeting，但连接任务一失败就立刻抛真实异常。

    入参 (data): conn(aioimaplib 连接, 必填)

    **不套信封**（纯副作用 + 失败即 raise，由 async_open_imap 捕获后转信封）。

    aioimaplib 的 TLS 握手跑在后台 create_connection 任务里，握手被拒后
    wait_hello_from_server 会一直等到 socket 超时（实测白等 12 秒才降级重试）。
    """
    if not isinstance(data, dict):
        raise ValueError("data 必须是字典对象")
    conn = data.get("conn")
    if conn is None:
        raise ValueError("缺少 conn 字段")
    hello = asyncio.ensure_future(conn.wait_hello_from_server())
    connect_task = conn._client_task
    try:
        done, _ = await asyncio.wait({hello, connect_task},
                                     return_when=asyncio.FIRST_COMPLETED)
        if hello not in done:
            exc = None if connect_task.cancelled() else connect_task.exception()
            if exc is not None:
                raise exc
            done, _ = await asyncio.wait({hello}, return_when=asyncio.ALL_COMPLETED)
        hello.result()
    finally:
        if not hello.done():
            hello.cancel()


async def async_open_imap(data: dict = None) -> Dict[str, Any]:
    """建 IMAP SSL 连接并等到服务端 greeting（TLS 协商失败自动按 imap_ssl_contexts 重试）。

    入参 (data):
        cfg(dict, 必填)      get_email_config 的产物（需 imap_host / imap_port）
        timeout(int, 可选)   连接超时秒数，默认 30

    返回:
        {"code":200, "data": aioimaplib.IMAP4_SSL, "message":"success"}   已等到 greeting
        {"code":500, "data": 位置, "message": "<host>:<port> 无法建立 TLS 连接：<原因>"}
        {"code":400, ...}  cfg 缺字段或类型非法
        端口 143 握手失败时 message 附带"请改用 993/SSL"指引

    全部尝试失败时返回**最后一个真实异常**的原因（原实现是 raise 它）。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "async_open_imap")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段（get_email_config 的产物）", "async_open_imap")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "async_open_imap")
    host = cfg.get("imap_host")
    if not host:
        return _err("cfg 缺少 imap_host 字段", "async_open_imap")
    if isinstance(host, (dict, list, tuple, set)):
        return _err(f"cfg.imap_host 必须是字符串，收到 {type(host).__name__}", "async_open_imap")
    port_raw = cfg.get("imap_port")
    if port_raw in (None, ""):
        return _err("cfg 缺少 imap_port 字段", "async_open_imap")
    if isinstance(port_raw, (dict, list, tuple, set)):
        return _err(f"cfg.imap_port 必须是整数，收到 {type(port_raw).__name__}", "async_open_imap")
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        return _err(f"cfg.imap_port 必须是整数，收到 {port_raw!r}", "async_open_imap")
    raw_timeout = data.get("timeout", 30)
    if raw_timeout in (None, ""):
        raw_timeout = 30
    if isinstance(raw_timeout, (dict, list, tuple, set)):
        return _err(f"timeout 必须是数字，收到 {type(raw_timeout).__name__}", "async_open_imap")
    try:
        timeout = float(raw_timeout)
    except (TypeError, ValueError):
        return _err("timeout 必须是数字", "async_open_imap")
    if timeout <= 0:
        return _err("timeout 必须大于 0", "async_open_imap")

    host = str(host)
    last: BaseException = RuntimeError(f"{host}:{port} 无法建立 TLS 连接")
    for r in imap_ssl_contexts():
        if r.get("code") != 200:
            return r
        ctx = r["data"]
        conn = None
        try:
            conn = aioimaplib.IMAP4_SSL(host, port, timeout=timeout, ssl_context=ctx)
            await _wait_imap_hello({"conn": conn})
            return _ok(conn)
        except Exception as e:
            ce = imap_connect_error({"e": e, "conn": conn})
            if ce.get("code") != 200:
                last = e
            else:
                last = ce["data"] if isinstance(ce["data"], BaseException) else e
            if conn is not None:
                await _abandon_imap({"conn": conn})
    if port == 143:
        return _err(f"{host}:143 握手失败，该端口通常是明文 IMAP（本平台不以明文提交授权码），"
                    f"请改用 993/SSL。原因：{last}", "async_open_imap", code=500)
    return _err(f"{host}:{port} 无法建立 TLS 连接。原因：{last}", "async_open_imap", code=500)


async def async_open_smtp(data: dict = None) -> Dict[str, Any]:
    """建 SMTP 连接并保证链路已加密，返回**未登录**的 aiosmtplib.SMTP。

    入参 (data):
        cfg(dict, 必填)    get_email_config 的产物（需 smtp_host / smtp_port）
        timeout(int, 可选) 连接超时秒数，默认 30

    返回:
        {"code":200, "data": aiosmtplib.SMTP, "message":"success"}
        {"code":500, ...} 未提供 TLS 或连接失败（已关闭半开连接）
        {"code":400, ...} cfg 缺字段或类型非法

    465 走隐式 TLS；其它端口由 aiosmtplib 机会性 STARTTLS 升级，升级不成（服务端不公告
    STARTTLS 或被中间设备拦截）就拒绝——否则授权码会以明文过网络。
    """
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "async_open_smtp")
    cfg = data.get("cfg")
    if cfg is None:
        return _err("缺少 cfg 字段", "async_open_smtp")
    if not isinstance(cfg, dict):
        return _err(f"cfg 必须是字典，收到 {type(cfg).__name__}", "async_open_smtp")
    host = cfg.get("smtp_host")
    if not host:
        return _err("cfg 缺少 smtp_host 字段", "async_open_smtp")
    if isinstance(host, (dict, list, tuple, set)):
        return _err(f"cfg.smtp_host 必须是字符串，收到 {type(host).__name__}", "async_open_smtp")
    port_raw = cfg.get("smtp_port")
    if port_raw in (None, ""):
        return _err("cfg 缺少 smtp_port 字段", "async_open_smtp")
    if isinstance(port_raw, (dict, list, tuple, set)):
        return _err(f"cfg.smtp_port 必须是整数，收到 {type(port_raw).__name__}", "async_open_smtp")
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        return _err(f"cfg.smtp_port 必须是整数，收到 {port_raw!r}", "async_open_smtp")
    raw_timeout = data.get("timeout", 30)
    if raw_timeout in (None, ""):
        raw_timeout = 30
    if isinstance(raw_timeout, (dict, list, tuple, set)):
        return _err(f"timeout 必须是数字，收到 {type(raw_timeout).__name__}", "async_open_smtp")
    try:
        timeout = float(raw_timeout)
    except (TypeError, ValueError):
        return _err("timeout 必须是数字", "async_open_smtp")
    if timeout <= 0:
        return _err("timeout 必须大于 0", "async_open_smtp")

    host = str(host)
    client = SMTP(hostname=host, port=port, use_tls=(port == 465), timeout=timeout)
    try:
        await client.connect()
    except Exception as e:
        try:
            client.close()
        except Exception:
            pass
        return _err(f"{host}:{port} 连接失败：{type(e).__name__}: {e}", "async_open_smtp", code=500)
    if port != 465 and client.get_transport_info("sslcontext") is None:
        client.close()
        return _err(f"{host}:{port} 未提供 TLS（隐式 TLS 与 STARTTLS 均不可用），"
                    f"拒绝明文提交授权码，请改用 465", "async_open_smtp", code=500)
    return _ok(client)
