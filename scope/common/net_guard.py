# -*- coding: utf-8 -*-
"""出站 URL 安全校验（SSRF 防护）。

平台里的网络工具（HTTP 请求、下载、浏览器抓取、在线 PDF）都接受用户可控的
URL。如果不做限制，登录用户可以让 Agent 访问 ``127.0.0.1``、内网网段或云厂商
元数据地址（``169.254.169.254``），从而探测 Redis / PostgreSQL / 管理接口。

本模块提供统一闸门：

- 只允许 ``http`` / ``https``；
- 禁止 URL 中携带用户名/密码；
- 主机名解析出的 **任意** 地址不是公网地址就拒绝（fail-closed）；
- 覆盖 IPv4 / IPv6 / IPv4-mapped / 6to4 / Teredo，以及回环、私网、链路本地、
  保留、组播、未指定、CGNAT 等特殊地址。

本模块不依赖任何工具域或模型层，可被 net / mcp 等出站组件复用。
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any, Iterable
from urllib.parse import urlsplit


class UnsafeUrl(ValueError):
    """URL 未通过出站安全校验。"""


def _embedded_ipv4(ip: Any) -> Iterable[Any]:
    """产出 IPv6 地址中内嵌的 IPv4 地址（用于检查映射/隧道地址）。"""
    if not isinstance(ip, ipaddress.IPv6Address):
        return ()
    values = []
    if ip.ipv4_mapped is not None:
        values.append(ip.ipv4_mapped)
    if ip.sixtofour is not None:
        values.append(ip.sixtofour)
    if ip.teredo is not None:
        server, client = ip.teredo
        values.extend([server, client])
    return values


def _is_public_ip(value: str) -> bool:
    """判断 IP 字符串是否为可访问的公网地址。"""
    raw = str(value).split("%", 1)[0]  # 去掉 IPv6 zone id（fe80::1%eth0）
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return False

    # IPv4-mapped IPv6（::ffff:127.0.0.1）必须按内层 IPv4 判断。
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped

    if not ip.is_global:
        return False

    # 6to4 / Teredo 可能把内网 IPv4 包在“看起来公网”的 IPv6 里。
    if any(not embedded.is_global for embedded in _embedded_ipv4(ip)):
        return False
    return True


def _normalize_host(host: str) -> str:
    value = str(host or "").strip().rstrip(".")
    if not value:
        raise UnsafeUrl("URL 缺少主机名")
    if value.lower() in ("localhost", "localhost.localdomain") or value.lower().endswith(".localhost"):
        raise UnsafeUrl("目标主机属于本机地址，已拒绝")
    try:
        # 非 ASCII 域名统一转成 IDNA，避免解析器与校验器看到不同的主机名。
        return value.encode("idna").decode("ascii") if not value.isascii() else value
    except UnicodeError as exc:
        raise UnsafeUrl(f"非法主机名：{exc}") from exc


def _parse_url(url: str) -> tuple[str, str, int]:
    if not isinstance(url, str) or not url.strip():
        raise UnsafeUrl("URL 不能为空")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url):
        raise UnsafeUrl("URL 包含非法控制字符")

    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise UnsafeUrl("仅允许 http/https 协议")
    if parts.username is not None or parts.password is not None:
        raise UnsafeUrl("URL 不允许包含用户名或密码")

    host = _normalize_host(parts.hostname or "")
    try:
        port = parts.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeUrl(f"URL 端口非法：{exc}") from exc
    if not (0 < port < 65536):
        raise UnsafeUrl("URL 端口非法")
    return scheme, host, port


def _resolve(host: str, port: int) -> list[str]:
    """解析主机名，返回去重后的 IP 字符串列表（DNS 失败即拒绝）。"""
    try:
        ipaddress.ip_address(host.split("%", 1)[0])
        return [host]
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeUrl(f"目标主机解析失败：{exc}") from exc

    addresses: list[str] = []
    for info in infos:
        addr = str(info[4][0])
        if addr not in addresses:
            addresses.append(addr)
    if not addresses:
        raise UnsafeUrl("目标主机没有解析到任何地址")
    return addresses


def check_url_sync(url: str) -> tuple[bool, str]:
    """同步校验 URL 是否可安全访问，返回 ``(allowed, reason)``。"""
    try:
        _, host, port = _parse_url(url)
        addresses = _resolve(host, port)
        for addr in addresses:
            if not _is_public_ip(addr):
                raise UnsafeUrl(f"目标地址 {addr} 属于内网/保留地址，已拒绝")
    except UnsafeUrl as exc:
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001 - 闸门必须 fail-closed
        return False, f"URL 安全校验失败：{type(exc).__name__}: {exc}"
    return True, ""


async def check_url(url: str) -> tuple[bool, str]:
    """异步校验 URL 是否可安全访问，返回 ``(allowed, reason)``。

    DNS 解析放到线程池，避免阻塞事件循环；解析失败按拒绝处理。
    """
    try:
        _, host, port = _parse_url(url)
        addresses = await asyncio.to_thread(_resolve, host, port)
        for addr in addresses:
            if not _is_public_ip(addr):
                raise UnsafeUrl(f"目标地址 {addr} 属于内网/保留地址，已拒绝")
    except UnsafeUrl as exc:
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001 - 闸门必须 fail-closed
        return False, f"URL 安全校验失败：{type(exc).__name__}: {exc}"
    return True, ""


__all__ = ["UnsafeUrl", "check_url", "check_url_sync"]
