"""知识库解析队列 worker：并发与排队顺序可配置。"""

import asyncio
import logging

from app.core.database import AsyncSessionLocal
from app.services.agent.knowledge import (
    async_auto_parse_once,
    async_claim_parse_documents,
    async_parse_config,
    async_run_claimed,
)

logger = logging.getLogger("knowledge.worker")


async def async_knowledge_worker(params: dict) -> None:
    """知识库解析 worker：自动入队并按配置并发解析。参数：stop。"""
    stop: asyncio.Event = params["stop"]
    while not stop.is_set():
        interval = 5
        try:
            async with AsyncSessionLocal() as session:
                config = await async_parse_config({"session": session})
                interval = config["worker_interval"]
                auto = await async_auto_parse_once({"session": session})
                if auto.get("processed"):
                    logger.info("知识库自动入队：%s 个文档", auto["processed"])
            async with AsyncSessionLocal() as session:
                config = await async_parse_config({"session": session})
                claimed = await async_claim_parse_documents(
                    {
                        "session": session,
                        "limit": config["parse_concurrency"],
                        "queue_mode": config["queue_mode"],
                    }
                )
            if claimed:
                semaphore = asyncio.Semaphore(config["parse_concurrency"])

                async def run_one(item: dict) -> None:
                    """执行单个已认领的解析任务。"""
                    async with semaphore:
                        try:
                            async with AsyncSessionLocal() as session:
                                await async_run_claimed(
                                    {"session": session, "document_id": item["document_id"]}
                                )
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("知识库解析失败 %s：%s", item["document_id"], exc)

                await asyncio.gather(*(run_one(item) for item in claimed))
                continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("知识库 worker 异常：%s", exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=max(2, interval))
        except asyncio.TimeoutError:
            pass
