"""知识库自动解析后台扫描。"""

import asyncio
import logging

from app.core.database import AsyncSessionLocal
from app.services.agent.knowledge import async_auto_parse_once

logger = logging.getLogger("knowledge.worker")


async def async_knowledge_worker(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            async with AsyncSessionLocal() as session:
                result = await async_auto_parse_once({"session": session})
                if result.get("processed"):
                    logger.info("知识库自动解析：%s 个文档", result["processed"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("知识库自动解析失败：%s", exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass
