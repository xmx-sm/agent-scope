"""默认配置路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import SuperAdmin, ok
from app.schemas import ConfigUpdateIn
from app.services.config import service as config_service

router = APIRouter(prefix="/admin/configs", tags=["默认配置"])


@router.get("")
async def list_configs(_: SuperAdmin, db: AsyncSession = Depends(get_db)):
    return ok(await config_service.async_list_configs({"session": db}))


@router.put("/{key}")
async def update_config(
    key: str, body: ConfigUpdateIn, operator: SuperAdmin, db: AsyncSession = Depends(get_db)
):
    return ok(
        await config_service.async_update_config(
            {"session": db, "key": key, "value": body.value, "operator_id": operator.id}
        ),
        "配置已保存",
    )


@router.post("/{key}/reset")
async def reset_config(key: str, operator: SuperAdmin, db: AsyncSession = Depends(get_db)):
    return ok(
        await config_service.async_reset_config(
            {"session": db, "key": key, "operator_id": operator.id}
        ),
        "已恢复默认值",
    )
