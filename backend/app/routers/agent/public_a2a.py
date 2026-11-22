"""A2A 数据面：X-Api-Key 鉴权，供局域网伙伴调用。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import ApiError, ok
from app.schemas.agent.collaboration import A2AInboundIn
from app.services.agent.collaboration import a2a as a2a_service

router = APIRouter(prefix="/a2a", tags=["A2A 互联"])


@router.get("/agents")
async def a2a_agents(request: Request, db: AsyncSession = Depends(get_db)):
    key = request.headers.get("X-Api-Key", "")
    peer = await a2a_service.resolve_inbound_peer({"session": db, "api_key": key})
    if peer is None:
        raise ApiError("密钥无效或伙伴未启用", code=401)
    return ok(await a2a_service.inbound_catalog({"peer": peer}))


@router.post("/invoke")
async def a2a_invoke(
    body: A2AInboundIn, request: Request, db: AsyncSession = Depends(get_db)
):
    return ok(
        await a2a_service.async_inbound_invoke(
            {
                "session": db,
                "api_key": request.headers.get("X-Api-Key", ""),
                "body": body,
            }
        )
    )
