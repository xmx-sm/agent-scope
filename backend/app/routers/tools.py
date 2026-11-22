"""AI 工具权限路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, SuperAdmin, ok, require_permission
from app.core.tools import TOOL_GROUPS
from app.models import User
from app.schemas import (
    ToolApprovalDecisionIn,
    ToolApprovalRequestIn,
    ToolApprovalRequiredIn,
    ToolNarrowIn,
    ToolPolicyIn,
    ToolSetIn,
)
from app.services.tools import audit as tool_audit
from app.services.tools import policy as tool_policy
from app.services.tools import command as tool_command
from app.services.tools import evaluate as tool_evaluate
from app.services.user.query import async_get_user_or_404

router = APIRouter(tags=["AI 工具权限"])


@router.get("/tools/catalog")
async def tool_catalog(_: CurrentUser):
    return ok(TOOL_GROUPS)


@router.get("/tools/mine")
async def my_tools(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await tool_evaluate.async_tool_view({"session": db, "user": user}))


@router.post("/tools/mine/narrow")
async def narrow_mine(
    body: ToolNarrowIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    data = await tool_command.async_narrow_tool(
        {
            "session": db,
            "actor": user,
            "target_id": user.id,
            "group": body.group,
            "tool": body.tool,
            "enabled": body.enabled,
        }
    )
    return ok(data, "工具权限已更新")


@router.post("/tools/mine/request")
async def request_tool_approval(
    body: ToolApprovalRequestIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    data = await tool_command.async_request_approval(
        {
            "session": db,
            "user": user,
            "group": body.group,
            "tool": body.tool,
            "reason": body.reason,
        }
    )
    return ok(data, "申请已提交")


@router.get("/tools/approvals")
async def list_tool_approvals(
    user: User = Depends(require_permission("permissions.team")),
    db: AsyncSession = Depends(get_db),
):
    return ok(await tool_command.async_list_approvals({"session": db, "actor": user}))


@router.post("/tools/approvals/{request_id}/decide")
async def decide_tool_approval(
    request_id: str,
    body: ToolApprovalDecisionIn,
    user: User = Depends(require_permission("permissions.team")),
    db: AsyncSession = Depends(get_db),
):
    data = await tool_command.async_decide_approval(
        {
            "session": db,
            "actor": user,
            "request_id": request_id,
            "approve": body.approve,
        }
    )
    return ok(data, "已通过" if body.approve else "已拒绝")


@router.post("/admin/users/{user_id}/tools/approval-required")
async def set_tool_approval_required(
    user_id: str,
    body: ToolApprovalRequiredIn,
    _: SuperAdmin,
    db: AsyncSession = Depends(get_db),
):
    target = await async_get_user_or_404({"session": db, "user_id": user_id})
    data = await tool_command.async_set_tool_approval(
        {
            "session": db,
            "target": target,
            "group": body.group,
            "tool": body.tool,
            "require_approval": body.require_approval,
        }
    )
    return ok(data, "审批设置已保存")


@router.get("/tools/team")
async def team_tools(
    user: User = Depends(require_permission("permissions.team")),
    db: AsyncSession = Depends(get_db),
):
    return ok(await tool_command.async_team_tools({"session": db, "viewer": user}))


@router.post("/tools/team/{user_id}/narrow")
async def narrow_team(
    user_id: str,
    body: ToolNarrowIn,
    user: User = Depends(require_permission("permissions.team")),
    db: AsyncSession = Depends(get_db),
):
    data = await tool_command.async_narrow_tool(
        {
            "session": db,
            "actor": user,
            "target_id": user_id,
            "group": body.group,
            "tool": body.tool,
            "enabled": body.enabled,
        }
    )
    return ok(data, "下级工具权限已更新")


@router.get("/admin/users/{user_id}/tools")
async def user_tools(user_id: str, _: SuperAdmin, db: AsyncSession = Depends(get_db)):
    target = await async_get_user_or_404({"session": db, "user_id": user_id})
    return ok(await tool_evaluate.async_tool_view({"session": db, "user": target}))


@router.put("/admin/users/{user_id}/tools")
async def set_user_tools(
    user_id: str, body: ToolSetIn, _: SuperAdmin, db: AsyncSession = Depends(get_db)
):
    target = await async_get_user_or_404({"session": db, "user_id": user_id})
    data = await tool_command.async_set_tools(
        {
            "session": db,
            "target": target,
            "data": body.model_dump(),
            "operator_id": _.id,
        }
    )
    return ok(data, "工具权限已保存")


@router.post("/tools/team/{user_id}/tighten")
async def tighten_team_mode(
    user_id: str,
    user: User = Depends(require_permission("permissions.team")),
    db: AsyncSession = Depends(get_db),
):
    data = await tool_command.async_tighten_mode(
        {"session": db, "actor": user, "target_id": user_id}
    )
    return ok(data, "已切换为按清单授权")


@router.get("/admin/tool-policy")
async def get_tool_policy(_: SuperAdmin, db: AsyncSession = Depends(get_db)):
    return ok(await tool_policy.async_get_policy({"session": db}))


@router.get("/admin/tool-policy/defaults")
async def get_tool_policy_defaults(_: SuperAdmin, db: AsyncSession = Depends(get_db)):
    return ok(await tool_policy.async_defaults_view({"session": db}))


@router.put("/admin/tool-policy")
async def set_tool_policy(
    body: ToolPolicyIn, _: SuperAdmin, db: AsyncSession = Depends(get_db)
):
    return ok(
        await tool_policy.async_set_policy({"session": db, "data": body.model_dump()}),
        "默认工具策略已保存",
    )


@router.get("/admin/tool-audits")
async def list_tool_audits(
    _: SuperAdmin,
    page: int = 1,
    page_size: int = 20,
    user_id: str = "",
    actor_id: str = "",
    db: AsyncSession = Depends(get_db),
):
    return ok(
        await tool_audit.async_list_audits(
            {
                "session": db,
                "page": page,
                "page_size": page_size,
                "user_id": user_id,
                "actor_id": actor_id,
            }
        )
    )


@router.post("/admin/users/{user_id}/tools/reset")
async def reset_user_tools(user_id: str, _: SuperAdmin, db: AsyncSession = Depends(get_db)):
    target = await async_get_user_or_404({"session": db, "user_id": user_id})
    data = await tool_command.async_reset_tools(
        {"session": db, "target": target, "operator_id": _.id}
    )
    return ok(data, "已恢复全部工具")
