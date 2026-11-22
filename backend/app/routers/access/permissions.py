"""权限路由：我的权限、团队权限、角色矩阵、用户权限配置。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, SuperAdmin, ok, require_permission
from app.core.permissions import PERMISSIONS
from app.models import User
from app.schemas import PermissionUpdateIn, UserPermissionUpdateIn
from app.services.access.permissions import admin as permission_admin
from app.services.access.permissions import evaluate as permission_evaluate
from app.services.access.permissions import role as permission_role
from app.services.access.permissions import shrink as permission_shrink
from app.services.access.permissions import team as permission_team

router = APIRouter(tags=["权限"])


@router.get("/permissions/mine")
async def my_permissions(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    detail = await permission_evaluate.async_permission_detail({"session": db, "user": user})
    detail["catalog"] = PERMISSIONS
    return ok(detail)


@router.post("/permissions/mine/shrink")
async def shrink_mine(
    body: PermissionUpdateIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    added = await permission_shrink.async_shrink_self(
        {"session": db, "user": user, "permissions": body.permissions}
    )
    return ok({"added": added}, "已收缩权限")


@router.get("/permissions/team")
async def team_permissions(
    user: User = Depends(require_permission("permissions.team")),
    db: AsyncSession = Depends(get_db),
):
    return ok(
        {
            "members": await permission_team.async_team_permissions({"session": db, "viewer": user}),
            "catalog": PERMISSIONS,
        }
    )


@router.post("/permissions/team/{user_id}/shrink")
async def shrink_member(
    user_id: str,
    body: PermissionUpdateIn,
    user: User = Depends(require_permission("permissions.team")),
    db: AsyncSession = Depends(get_db),
):
    added = await permission_shrink.async_shrink_member(
        {
            "session": db,
            "actor": user,
            "target_id": user_id,
            "permissions": body.permissions,
        }
    )
    return ok({"added": added}, "已收缩下属权限")


@router.get("/admin/users/{user_id}/permissions")
async def user_permissions(user_id: str, _: SuperAdmin, db: AsyncSession = Depends(get_db)):
    return ok(await permission_admin.async_user_permission_detail(
        {"session": db, "user_id": user_id}
    ))


@router.put("/admin/users/{user_id}/permissions")
async def set_user_permissions(
    user_id: str,
    body: UserPermissionUpdateIn,
    operator: SuperAdmin,
    db: AsyncSession = Depends(get_db),
):
    return ok(
        await permission_admin.async_set_user_permissions(
            {
                "session": db,
                "user_id": user_id,
                "data": body.model_dump(),
                "operator_id": operator.id,
            }
        ),
        "权限已保存",
    )


@router.get("/admin/permissions")
async def list_permissions(_: SuperAdmin, db: AsyncSession = Depends(get_db)):
    return ok(await permission_role.async_list_permissions({"session": db}))


@router.put("/admin/permissions/{role}")
async def update_permissions(
    role: str, body: PermissionUpdateIn, _: SuperAdmin, db: AsyncSession = Depends(get_db)
):
    return ok(
        await permission_role.async_update_permissions(
            {"session": db, "role": role, "permissions": body.permissions}
        ),
        "权限已保存",
    )
