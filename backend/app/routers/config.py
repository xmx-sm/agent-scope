"""默认配置路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import SuperAdmin, ok
from app.schemas import ConfigUpdateIn, DbAccessCheckIn, ModelFetchIn
from app.services.config import agent as agent_service
from app.services.config import service as config_service
from app.services.security import db_policy as db_policy_service

router = APIRouter(tags=["配置"])


@router.get("/admin/configs")
async def list_configs(
    _: SuperAdmin, domain: str = "", db: AsyncSession = Depends(get_db)
):
    return ok(
        await config_service.async_list_configs({"session": db, "domain": domain})
    )


@router.get("/admin/security/policy")
async def get_security_policy(_: SuperAdmin, db: AsyncSession = Depends(get_db)):
    policy = await db_policy_service.async_get_db_policy({"session": db})
    prompt_enabled = await config_service.async_get_config(
        {"session": db, "key": "security.prompt_guard_enabled", "default": True}
    )
    identity_lock = await config_service.async_get_config(
        {"session": db, "key": "security.identity_lock", "default": True}
    )
    allow_paths = await config_service.async_get_config(
        {"session": db, "key": "security.allow_model_file_paths", "default": False}
    )
    return ok(
        {
            "db_policy": policy,
            "prompt_guard_enabled": bool(prompt_enabled),
            "identity_lock": bool(identity_lock),
            "allow_model_file_paths": bool(allow_paths),
        }
    )


@router.post("/admin/security/db/check")
async def check_db_access(
    body: DbAccessCheckIn, _: SuperAdmin, db: AsyncSession = Depends(get_db)
):
    policy = await db_policy_service.async_get_db_policy({"session": db})
    allowed = db_policy_service.is_table_allowed(policy, body.database, body.table)
    return ok({"database": body.database, "table": body.table, "allowed": allowed})


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
