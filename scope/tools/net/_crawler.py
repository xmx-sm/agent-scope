

"""
AsyncWebCrawler 进程级单例：惰性创建、并发启动保护、按次数回收。

_CRAWLER / _START_LOCK 为模块级可变全局，与本文件函数同模块（依赖 global 语义），勿外移。

`_get_crawler` 返回活对象故套信封；`_reset_crawler` 是**纯副作用**（关单例、置 None），
不套信封——它无数据可返回，失败也不该阻断调用方（原实现即吞掉 close 的异常）。

crawl4ai 为可选依赖，采用函数内延迟导入：未安装时本模块仍可加载，
仅 _get_crawler 进入创建分支时返回 500 信封（原实现裸抛 ModuleNotFoundError）。
"""


import threading
from typing import Any, Dict

from ._envelope import _err, _ok

# ========== 浏览器实例单例 ==========
_CRAWLER = None

_START_LOCK = threading.Lock()


async def _get_crawler(data: dict = None) -> Dict[str, Any]:
    """获取进程级 AsyncWebCrawler 单例（懒创建；_START_LOCK 防并发重复启动）。

    入参 (data):
        browser_cfg(配置对象, 可选) 仅首次创建时使用；已有单例时**不会**因此改变
                                    （原实现即如此：单例一旦建立，后续 browser_cfg 被忽略）

    返回:
        {"code":200, "data": <AsyncWebCrawler 实例>, "message":"success"}
        data 直接是活对象（不可 JSON 序列化），调用方取出后 .arun(url, config=run_cfg)
        {"code":500, "data": 位置, "message": 创建失败原因}

    ⚠️ 未安装 crawl4ai 时返回 500 信封而非抛 ModuleNotFoundError，
    使本域错误形状统一（调用方只需判 code）。
    """
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _err("data 必须是字典对象", "_get_crawler")
    browser_cfg = data.get("browser_cfg")
    global _CRAWLER
    if _CRAWLER is not None:
        return _ok(_CRAWLER)
    try:
        from crawl4ai import AsyncWebCrawler
    except ImportError:
        # 400 而非 500：驱动未装是**部署前置条件不满足**，与 db 域 asyncpg/aiomysql
        # 缺失的处理一致（_pg_exec 同样回 400），跨域不制造第二种错误形状。
        return _err("未安装 crawl4ai（pip install crawl4ai），"
                    "该工具为可选依赖，其余网络功能不受影响", "_get_crawler")
    with _START_LOCK:
        if _CRAWLER is None:
            try:
                c = AsyncWebCrawler(config=browser_cfg, thread_safe=True)
                await c.start()
            except Exception as e:
                return _err(f"浏览器启动失败：{type(e).__name__}: {e}",
                            "_get_crawler", code=500)
            _CRAWLER = c
    return _ok(_CRAWLER)


async def _reset_crawler(data: dict = None) -> None:
    """关掉并清空单例，下次调用重建（自愈用：抓取异常后避免复用坏掉的浏览器）。

    入参 (data): 无字段使用，可为 None 或 {}

    **不套信封**（纯副作用，返回 None）。close 失败被吞掉——清理失败不该掩盖原始抓取错误。
    """
    global _CRAWLER
    c, _CRAWLER = _CRAWLER, None
    if c is not None:
        try:
            await c.close()
        except Exception:
            pass
