"""默认配置路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import SuperAdmin, ok
from app.schemas import ConfigUpdateIn, ModelFetchIn
from app.services.config import agent as agent_service
from app.services.config import service as config_service

router = APIRouter(tags=["配置"])


@router.get("/admin/configs")
async def list_configs(
    _: SuperAdmin, domain: str = "", db: AsyncSession = Depends(get_db)
):
    return ok(
        await config_service.async_list_configs({"session": db, "domain": domain})
    )


@router.get("/admin/agent/providers")
async def list_providers(_: SuperAdmin, db: AsyncSession = Depends(get_db)):
    return ok(await agent_service.async_list_providers({}))


@router.post("/admin/agent/models")
async def fetch_models(body: ModelFetchIn, _: SuperAdmin, db: AsyncSession = Depends(get_db)):
    return ok(
        await agent_service.async_fetch_models(
            {
                "provider": body.provider,
                "base_url": body.base_url,
                "api_key": body.api_key,
                "key_config": body.key_config,
                "session": db,
            }
        ),
        "模型列表已获取",
    )


@router.put("/admin/configs/{key}")
async def update_config(
    key: str, body: ConfigUpdateIn, operator: SuperAdmin, db: AsyncSession = Depends(get_db)
):
    return ok(
        await config_service.async_update_config(
            {"session": db, "key": key, "value": body.value, "operator_id": operator.id}
        ),
        "配置已保存",
    )


@router.post("/admin/configs/{key}/reset")
async def reset_config(key: str, operator: SuperAdmin, db: AsyncSession = Depends(get_db)):
    return ok(
        await config_service.async_reset_config(
            {"session": db, "key": key, "operator_id": operator.id}
        ),
        "已恢复默认值",
    )
