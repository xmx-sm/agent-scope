"""宿主机运行状态采集：CPU、内存、磁盘、GPU、网络、Redis、数据库。"""

import asyncio
import platform
import socket
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

import psutil
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.utils.redis_util import async_get_redis_client

_STARTED_AT = time.time()


def _safe(fn, default=None):
    """内部辅助函数：_safe。
    参数：fn / default。
    """
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _cpu_info() -> dict[str, Any]:
    """内部辅助函数：_cpu_info。
    参数：无。
    """
    freq = _safe(psutil.cpu_freq)
    load = _safe(psutil.getloadavg)
    return {
        "usage_percent": psutil.cpu_percent(interval=0.15),
        "logical": psutil.cpu_count(logical=True),
        "physical": psutil.cpu_count(logical=False),
        "frequency_mhz": round(freq.current, 1) if freq else None,
        "load_avg": [round(x, 2) for x in load] if load else None,
    }


def _memory_info() -> dict[str, Any]:
    """内部辅助函数：_memory_info。
    参数：无。
    """
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "total": mem.total,
        "used": mem.used,
        "available": mem.available,
        "percent": mem.percent,
        "swap_total": swap.total,
        "swap_used": swap.used,
        "swap_percent": swap.percent,
    }


def _disk_info() -> dict[str, Any]:
    """内部辅助函数：_disk_info。
    参数：无。
    """
    partitions = []
    seen = set()
    for part in psutil.disk_partitions(all=False):
        if part.mountpoint in seen:
            continue
        seen.add(part.mountpoint)
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        partitions.append(
            {
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent,
            }
        )
    io = _safe(psutil.disk_io_counters)
    return {
        "partitions": partitions,
        "io": {
            "read_bytes": io.read_bytes,
            "write_bytes": io.write_bytes,
            "read_count": io.read_count,
            "write_count": io.write_count,
        }
        if io
        else None,
    }


def _local_ips() -> list[dict[str, str]]:
    """内部辅助函数：_local_ips。
    参数：无。
    """
    result = []
    for name, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET:
                result.append({"interface": name, "address": addr.address, "netmask": addr.netmask})
    return result


def _primary_ip() -> str | None:
    """内部辅助函数：_primary_ip。
    参数：无。
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return None


def _network_info() -> dict[str, Any]:
    """内部辅助函数：_network_info。
    参数：无。
    """
    io = psutil.net_io_counters()
    return {
        "bytes_sent": io.bytes_sent,
        "bytes_recv": io.bytes_recv,
        "packets_sent": io.packets_sent,
        "packets_recv": io.packets_recv,
        "connections": len(_safe(psutil.net_connections, []) or []),
        "hostname": socket.gethostname(),
        "primary_ip": _primary_ip(),
        "interfaces": _local_ips(),
    }


def _gpu_info() -> list[dict[str, Any]]:
    """内部辅助函数：_gpu_info。
    参数：无。
    """
    query = (
        "index,name,memory.total,memory.used,memory.free,"
        "utilization.gpu,temperature.gpu,driver_version"
    )
    try:
        output = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []
    if output.returncode != 0:
        return []
    gpus = []
    for line in output.stdout.strip().splitlines():
        parts = [item.strip() for item in line.split(",")]
        if len(parts) < 8:
            continue
        try:
            gpus.append(
                {
                    "index": int(parts[0]),
                    "name": parts[1],
                    "memory_total_mb": int(parts[2]),
                    "memory_used_mb": int(parts[3]),
                    "memory_free_mb": int(parts[4]),
                    "utilization_percent": int(parts[5]),
                    "temperature_c": int(parts[6]),
                    "driver_version": parts[7],
                }
            )
        except ValueError:
            continue
    return gpus


def _process_info() -> dict[str, Any]:
    """内部辅助函数：_process_info。
    参数：无。
    """
    counts = {"running": 0, "sleeping": 0, "other": 0}
    for proc in psutil.process_iter(["status"]):
        try:
            status = proc.info["status"]
            if status == psutil.STATUS_RUNNING:
                counts["running"] += 1
            elif status == psutil.STATUS_SLEEPING:
                counts["sleeping"] += 1
            else:
                counts["other"] += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    counts["total"] = sum(counts.values())
    return counts


async def _redis_info() -> dict[str, Any]:
    """内部辅助函数：_redis_info。
    参数：无。
    """
    client = await async_get_redis_client(force=True)
    if client is None:
        return {
            "connected": False,
            "host": settings.redis_host,
            "port": settings.redis_port,
            "backend": "memory",
        }
    try:
        info = await client.info()
        return {
            "connected": True,
            "host": settings.redis_host,
            "port": settings.redis_port,
            "version": info.get("redis_version"),
            "mode": info.get("redis_mode"),
            "uptime_seconds": info.get("uptime_in_seconds"),
            "used_memory": info.get("used_memory"),
            "used_memory_human": info.get("used_memory_human"),
            "connected_clients": info.get("connected_clients"),
            "total_connections_received": info.get("total_connections_received"),
            "total_commands_processed": info.get("total_commands_processed"),
            "keyspace_hits": info.get("keyspace_hits"),
            "keyspace_misses": info.get("keyspace_misses"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "connected": False,
            "host": settings.redis_host,
            "port": settings.redis_port,
            "error": str(exc),
            "backend": "memory",
        }


async def _database_info(params: dict) -> dict[str, Any]:
    """内部辅助函数：_database_info。
    参数：session。
    """
    session: AsyncSession = params["session"]
    started = time.perf_counter()
    try:
        await session.execute(text("SELECT 1"))
        elapsed = (time.perf_counter() - started) * 1000
        target = settings.database_url.split("@")[-1] if "@" in settings.database_url else "unknown"
        return {
            "connected": True,
            "response_time_ms": round(elapsed, 2),
            "target": target,
        }
    except Exception as exc:  # noqa: BLE001
        return {"connected": False, "error": str(exc)}


async def async_system_status(params: dict) -> dict[str, Any]:
    """采集系统运行状态

    参数：session
    """
    session: AsyncSession = params["session"]
    cpu = await asyncio.to_thread(_cpu_info)
    memory = await asyncio.to_thread(_memory_info)
    disk = await asyncio.to_thread(_disk_info)
    network = await asyncio.to_thread(_network_info)
    gpu = await asyncio.to_thread(_gpu_info)
    process = await asyncio.to_thread(_process_info)
    redis = await _redis_info()
    database = await _database_info({"session": session})

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "app": {
            "name": settings.app_name,
            "env": settings.app_env,
            "uptime_seconds": int(time.time() - _STARTED_AT),
            "python": platform.python_version(),
        },
        "system": {
            "system": platform.system(),
            "node": platform.node(),
            "release": platform.release(),
            "machine": platform.machine(),
            "boot_time": datetime.fromtimestamp(
                psutil.boot_time(), tz=timezone.utc
            ).isoformat(),
        },
        "cpu": cpu,
        "memory": memory,
        "disk": disk,
        "gpu": gpu,
        "network": network,
        "process": process,
        "redis": redis,
        "database": database,
    }
