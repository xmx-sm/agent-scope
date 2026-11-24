"""A2A 数据面：X-Api-Key 鉴权，供局域网伙伴调用。"""

from fastapi import APIRouter, Depends, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import ApiError, ok
from app.schemas.agent.collaboration import A2AInboundIn
from app.services.agent.collaboration import a2a as a2a_service

router = APIRouter(prefix="/a2a", tags=["A2A 互联"])
a2a_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)


@router.get("/agents")
async def a2a_agents(
    db: AsyncSession = Depends(get_db),
    api_key: str | None = Security(a2a_key_header),
):
    peer = await a2a_service.resolve_inbound_peer({"session": db, "api_key": api_key or ""})
    if peer is None:
        raise ApiError("密钥无效或伙伴未启用", code=401)
    return ok(await a2a_service.inbound_catalog({"peer": peer}))


@router.post("/invoke")
async def a2a_invoke(
    body: A2AInboundIn,
    db: AsyncSession = Depends(get_db),
    api_key: str | None = Security(a2a_key_header),
):
    return ok(
        await a2a_service.async_inbound_invoke(
            {
                "session": db,
                "api_key": api_key or "",
                "body": body,
            }
        )
    )
