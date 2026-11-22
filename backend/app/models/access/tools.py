"""AI 工具权限、审批、审计与工具连接配置模型。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import new_id, utc_now


class UserToolMode(Base):
    """用户 AI 工具权限模式：all=全部工具可用 / custom=仅按清单授权。"""

    __tablename__ = "user_tool_modes"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="all")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class UserToolPermission(Base):
    """用户 AI 工具授权/收窄行。

    tool_name 为空串表示整个工具组。
    enabled=True 且 granted_by 为空：超管在 custom 模式下的授权。
    enabled=False：超管或上级/本人对该工具（组）的收窄。
    """

    __tablename__ = "user_tool_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "tool_group", "tool_name", name="uq_user_tool_perm"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_group: Mapped[str] = mapped_column(String(60), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    require_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_status: Mapped[str] = mapped_column(String(20), nullable=False, default="approved")
    granted_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ToolPermissionAudit(Base):
    """AI 工具权限变更留痕。"""

    __tablename__ = "tool_permission_audits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    tool_group: Mapped[str | None] = mapped_column(String(60), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prev_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ToolPolicy(Base):
    """新用户 AI 工具默认策略（单行，id=1）。"""

    __tablename__ = "tool_policies"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    new_user_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="all")
    default_grants: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class UserToolConfig(Base):
    """用户工具连接配置（邮箱 / 数据库）。"""

    __tablename__ = "user_tool_configs"
    __table_args__ = (
        UniqueConstraint("user_id", "category", name="uq_user_tool_config"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    use_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config_data: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ToolApprovalRequest(Base):
    """AI 工具使用审批请求。"""

    __tablename__ = "tool_approval_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    tool_group: Mapped[str] = mapped_column(String(60), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    approved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
