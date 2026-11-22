"""用户相关路由：个人资料、用户管理、用户统计。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, SuperAdmin, ok
from app.schemas import ProfileUpdateIn, ResetPasswordIn, UserCreateIn, UserUpdateIn
from app.services.user import command as user_command
from app.services.user import profile as profile_service
from app.services.user import query as user_query

router = APIRouter(tags=["用户"])


@router.put("/profile")
async def update_profile(
    body: ProfileUpdateIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    data = await profile_service.async_update_profile(
        {"session": db, "user": user, "data": body.model_dump()}
    )
    return ok(data, "资料已更新")


@router.get("/admin/stats")
async def stats(_: SuperAdmin, db: AsyncSession = Depends(get_db)):
    return ok(await user_query.async_stats({"session": db}))


@router.get("/admin/users")
async def list_users(
    viewer: SuperAdmin,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    keyword: str = "",
    role: str = "",
    db: AsyncSession = Depends(get_db),
):
    return ok(await user_query.async_list_users(
        {
            "session": db,
            "page": page,
            "page_size": page_size,
            "keyword": keyword,
            "role": role,
            "viewer": viewer,
        }
    ))


@router.post("/admin/users")
async def create_user(
    body: UserCreateIn, operator: SuperAdmin, db: AsyncSession = Depends(get_db)
):
    return ok(
        await user_command.async_create_user(
        {"session": db, "data": body.model_dump(), "operator": operator}
    ),
        "用户已创建",
    )


@router.put("/admin/users/{user_id}")
async def update_user(
    user_id: str, body: UserUpdateIn, operator: SuperAdmin, db: AsyncSession = Depends(get_db)
):
    return ok(
        await user_command.async_update_user(
            {
                "session": db,
                "user_id": user_id,
                "data": body.model_dump(exclude_unset=True),
                "operator": operator,
            }
        ),
        "用户已更新",
    )


@router.delete("/admin/users/{user_id}")
async def delete_user(user_id: str, operator: SuperAdmin, db: AsyncSession = Depends(get_db)):
    await user_command.async_delete_user(
        {"session": db, "user_id": user_id, "operator": operator}
    )
    return ok(None, "用户已删除")


@router.post("/admin/users/{user_id}/reset-password")
async def reset_password(
    user_id: str, body: ResetPasswordIn, operator: SuperAdmin, db: AsyncSession = Depends(get_db)
):
    await user_command.async_reset_password(
        {
            "session": db,
            "user_id": user_id,
            "new_password": body.new_password,
            "operator": operator,
        }
    )
    return ok(None, "密码已重置")
