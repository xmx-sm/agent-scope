"""AI 工具授权、模式切换与逐级收窄。"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.core.tools import GROUP_MAP, is_valid
from app.models import User, UserToolMode, UserToolPermission
from app.services.access.tools.audit import add_audit, snapshot
from app.services.access.tools.evaluate import async_tool_view
from app.services.account.user.tree import async_is_descendant


async def _async_set_mode(session: AsyncSession, user_id: str, mode: str) -> None:
    if mode not in ("all", "custom"):
        raise ApiError("tool_mode 只允许 all/custom")
    row = await session.get(UserToolMode, user_id)
    if row is None:
        session.add(UserToolMode(user_id=user_id, mode=mode))
    else:
        row.mode = mode


async def async_set_tools(params: dict) -> dict:
    """超管全量设置：模式 + custom 清单。参数：session / target / data"""
    session: AsyncSession = params["session"]
    target: User = params["target"]
    data: dict = params["data"]
    mode = data.get("mode") or "all"
    if mode not in ("all", "custom"):
        raise ApiError("tool_mode 只允许 all/custom")

    await session.execute(
        delete(UserToolPermission).where(UserToolPermission.user_id == target.id)
    )
    await _async_set_mode(session, target.id, mode)
    await add_audit(
        session,
        user_id=target.id,
        actor_id=params.get("operator_id") or target.id,
        action="set_mode",
        after=mode,
    )
    if mode == "custom":
        items = data.get("items") or []
        seen: set[tuple[str, str]] = set()
        for item in items:
            group = str(item.get("group") or "")
            tool = str(item.get("tool") or "")
            if not is_valid(group, tool):
                continue
            key = (group, tool)
            if key in seen:
                continue
            seen.add(key)
            session.add(
                UserToolPermission(
                    user_id=target.id,
                    tool_group=group,
                    tool_name=tool,
                    enabled=True,
                    granted_by=None,
                )
            )
        if not seen:
            raise ApiError("按清单授权时至少选择一个工具或工具组")
    await session.commit()
    return await async_tool_view({"session": session, "user": target})


async def async_reset_tools(params: dict) -> dict:
    """超管恢复默认：全部工具、清空所有收窄。参数：session / target"""
    session: AsyncSession = params["session"]
    target: User = params["target"]
    await session.execute(
        delete(UserToolPermission).where(UserToolPermission.user_id == target.id)
    )
    await _async_set_mode(session, target.id, "all")
    await add_audit(
        session,
        user_id=target.id,
        actor_id=params.get("operator_id") or target.id,
        action="reset",
        after="all",
    )
    await session.commit()
    return await async_tool_view({"session": session, "user": target})


async def async_narrow_tool(params: dict) -> dict:
    """上级/本人收窄工具。参数：session / actor / target_id / group / tool / enabled"""
    session: AsyncSession = params["session"]
    actor: User = params["actor"]
    target_id: str = params["target_id"]
    group: str = str(params.get("group") or "")
    tool: str = str(params.get("tool") or "")
    enabled: bool = bool(params.get("enabled"))

    if not is_valid(group, tool):
        raise ApiError("未知工具或工具组")
    if target_id != actor.id:
        if actor.role == "super_admin":
            pass
        elif not await async_is_descendant(
            {"session": session, "ancestor_id": actor.id, "target_id": target_id}
        ):
            raise ApiError("只能管理自己的下属", code=403)
    target = await session.get(User, target_id)
    if target is None:
        raise ApiError("用户不存在", code=404)

    existing = (
        await session.execute(
            select(UserToolPermission).where(
                UserToolPermission.user_id == target_id,
                UserToolPermission.tool_group == group,
                UserToolPermission.tool_name == tool,
            )
        )
    ).scalar_one_or_none()

    before = snapshot(existing.enabled if existing else None,
                      existing.granted_by if existing else None)
    if enabled:
        # 恢复=删除本人收窄行；其他上级的收窄行仍然生效
        if existing is not None and existing.granted_by == actor.id:
            await session.delete(existing)
    else:
        if target_id == actor.id and actor.role == "super_admin":
            raise ApiError("超级管理员无需收缩自己")
        if existing is None:
            session.add(
                UserToolPermission(
                    user_id=target_id,
                    tool_group=group,
                    tool_name=tool,
                    enabled=False,
                    granted_by=actor.id,
                )
            )
        else:
            existing.enabled = False
            existing.granted_by = actor.id
    await add_audit(
        session,
        user_id=target_id,
        actor_id=actor.id,
        action="grant_tool" if enabled else "narrow_tool",
        tool_group=group,
        tool_name=tool,
        before=before,
        after=snapshot(enabled, actor.id),
    )
    await session.commit()
    return await async_tool_view({"session": session, "user": target})


async def async_team_tools(params: dict) -> list[dict]:
    """参数：session / viewer，返回下属及工具权限概览。"""
    session: AsyncSession = params["session"]
    viewer: User = params["viewer"]
    from app.services.account.user.tree import async_descendants

    users = await async_descendants({"session": session, "user_id": viewer.id})
    result = []
    for user in users:
        view = await async_tool_view({"session": session, "user": user})
        result.append(
            {
                "id": user.id,
                "username": user.username,
                "nickname": user.nickname,
                "role": user.role,
                "mode": view["mode"],
                "enabled_count": view["enabled_count"],
                "total_count": view["total_count"],
                "groups": view["groups"],
            }
        )
    return result


async def async_tighten_mode(params: dict) -> dict:
    """上级把下属从「全部工具」收紧为「按清单授权」，先快照当前可用工具，功能不中断。
    参数：session / actor / target_id
    """
    session: AsyncSession = params["session"]
    actor: User = params["actor"]
    target_id: str = params["target_id"]
    if target_id != actor.id:
        if actor.role != "super_admin" and not await async_is_descendant(
            {"session": session, "ancestor_id": actor.id, "target_id": target_id}
        ):
            raise ApiError("只能管理自己的下属", code=403)
    target = await session.get(User, target_id)
    if target is None:
        raise ApiError("用户不存在", code=404)

    view = await async_tool_view({"session": session, "user": target})
    if view["mode"] == "custom":
        return view

    items = []
    for group in view["groups"]:
        enabled_tools = [tool for tool in group["tools"] if tool["enabled"]]
        if not enabled_tools:
            continue
        if len(enabled_tools) == len(group["tools"]):
            items.append({"group": group["name"], "tool": ""})
        else:
            items.extend(
                {"group": group["name"], "tool": tool["name"]} for tool in enabled_tools
            )

    await session.execute(
        delete(UserToolPermission).where(UserToolPermission.user_id == target.id)
    )
    await _async_set_mode(session, target.id, "custom")
    for item in items:
        session.add(
            UserToolPermission(
                user_id=target.id,
                tool_group=item["group"],
                tool_name=item["tool"],
                enabled=True,
                granted_by=None,
            )
        )
    await add_audit(
        session,
        user_id=target.id,
        actor_id=actor.id,
        action="tighten_mode",
        before="all",
        after=f"custom:{len(items)}",
    )
    await session.commit()
    return await async_tool_view({"session": session, "user": target})


async def async_request_approval(params: dict) -> dict:
    """用户为已授权但需审批的工具提交申请。参数：session / user / group / tool / reason"""
    session: AsyncSession = params["session"]
    user: User = params["user"]
    group: str = str(params.get("group") or "")
    tool: str = str(params.get("tool") or "")
    if not is_valid(group, tool):
        raise ApiError("未知工具或工具组")
    view = await async_tool_view({"session": session, "user": user})
    target = None
    for g in view["groups"]:
        if g["name"] != group:
            continue
        for item in g["tools"]:
            if item["name"] == tool:
                target = item
                break
    if target is None:
        raise ApiError("未知工具")
    if not target["granted"]:
        raise ApiError("该工具不在当前授权范围内，请联系管理员")

    from app.models import ToolApprovalRequest
    existing = (
        await session.execute(
            select(ToolApprovalRequest).where(
                ToolApprovalRequest.user_id == user.id,
                ToolApprovalRequest.tool_group == group,
                ToolApprovalRequest.tool_name == tool,
                ToolApprovalRequest.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            ToolApprovalRequest(
                user_id=user.id,
                tool_group=group,
                tool_name=tool,
                reason=str(params.get("reason") or ""),
                status="pending",
            )
        )

    row = (
        await session.execute(
            select(UserToolPermission).where(
                UserToolPermission.user_id == user.id,
                UserToolPermission.tool_group == group,
                UserToolPermission.tool_name == tool,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(
            UserToolPermission(
                user_id=user.id,
                tool_group=group,
                tool_name=tool,
                enabled=True,
                require_approval=True,
                approval_status="pending",
                granted_by=None,
            )
        )
    else:
        row.require_approval = True
        row.approval_status = "pending"
    await session.commit()
    return await async_tool_view({"session": session, "user": user})


async def async_list_approvals(params: dict) -> list[dict]:
    """参数：session / actor"""
    from app.models import ToolApprovalRequest
    from app.services.account.user.tree import async_descendants

    session: AsyncSession = params["session"]
    actor: User = params["actor"]
    stmt = select(ToolApprovalRequest).where(ToolApprovalRequest.status == "pending")
    if actor.role != "super_admin":
        users = await async_descendants({"session": session, "user_id": actor.id})
        ids = [u.id for u in users]
        if not ids:
            return []
        stmt = stmt.where(ToolApprovalRequest.user_id.in_(ids))
    rows = (await session.execute(stmt.order_by(ToolApprovalRequest.created_at.desc()))).scalars().all()
    names = {}
    if rows:
        users = (
            await session.execute(select(User).where(User.id.in_([r.user_id for r in rows])))
        ).scalars().all()
        names = {u.id: (u.nickname or u.username) for u in users}
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "user_name": names.get(r.user_id, r.user_id),
            "tool_group": r.tool_group,
            "tool_name": r.tool_name,
            "reason": r.reason,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


async def async_decide_approval(params: dict) -> dict:
    """参数：session / actor / request_id / approve"""
    from app.models import ToolApprovalRequest

    session: AsyncSession = params["session"]
    actor: User = params["actor"]
    request = await session.get(ToolApprovalRequest, params["request_id"])
    if request is None:
        raise ApiError("审批请求不存在", code=404)
    if request.status != "pending":
        raise ApiError("该申请已处理")
    if actor.role != "super_admin" and not await async_is_descendant(
        {"session": session, "ancestor_id": actor.id, "target_id": request.user_id}
    ):
        raise ApiError("该申请不在您的管辖范围内", code=403)
    approve = bool(params.get("approve"))
    request.status = "approved" if approve else "denied"
    request.approved_by = actor.id
    request.decided_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)

    row = (
        await session.execute(
            select(UserToolPermission).where(
                UserToolPermission.user_id == request.user_id,
                UserToolPermission.tool_group == request.tool_group,
                UserToolPermission.tool_name == request.tool_name,
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        row.require_approval = True
        row.approval_status = "approved" if approve else "denied"
    await session.commit()
    return {"request_id": request.id, "status": request.status}


async def async_set_tool_approval(params: dict) -> dict:
    """超管设置某工具是否需要审批。参数：session / target / group / tool / require_approval"""
    session: AsyncSession = params["session"]
    target: User = params["target"]
    group: str = str(params.get("group") or "")
    tool: str = str(params.get("tool") or "")
    required = bool(params.get("require_approval"))
    if not is_valid(group, tool):
        raise ApiError("未知工具或工具组")
    row = (
        await session.execute(
            select(UserToolPermission).where(
                UserToolPermission.user_id == target.id,
                UserToolPermission.tool_group == group,
                UserToolPermission.tool_name == tool,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(
            UserToolPermission(
                user_id=target.id,
                tool_group=group,
                tool_name=tool,
                enabled=True,
                require_approval=required,
                approval_status="pending" if required else "approved",
                granted_by=None,
            )
        )
    else:
        row.require_approval = required
        row.approval_status = "pending" if required else "approved"
    await session.commit()
    return await async_tool_view({"session": session, "user": target})
