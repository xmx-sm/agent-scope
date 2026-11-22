"""用户与用户权限状态模型。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import new_id, utc_now


class User(Base):
    """用户表。

    role: super_admin | admin | user
    leader_id: 直属上级（组织汇报线），NULL 表示无上级。
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    nickname: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user", index=True)
    leader_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class UserPermissionState(Base):
    """用户级权限状态（权限逐级收缩模型）。

    granted:  超管单独授予的权限（永久，叠加在角色权限之上）
    shrunk:   被上级或本人收缩掉的权限（只增不减，只有超管可清空）
    temp_grants: 超管临时越级授权，JSON: [{"permission": "...", "expires_at": "ISO时间"}]
    """

    __tablename__ = "user_permission_states"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    granted: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    shrunk: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    temp_grants: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
