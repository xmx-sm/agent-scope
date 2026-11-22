"""菜单配置模型。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import new_id, utc_now


class Menu(Base):
    """可配置菜单。

    parent_key 为空表示一级菜单；有 parent_key 时挂在该分组下。
    path 为空表示纯分组节点。
    permission 为空表示不校验权限点；super_only 表示仅超级管理员可见。
    """

    __tablename__ = "menus"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    parent_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(60), nullable=False)
    path: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    icon: Mapped[str] = mapped_column(String(60), nullable=False, default="Menu")
    permission: Mapped[str | None] = mapped_column(String(80), nullable=True)
    super_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    leader_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class UserMenuPref(Base):
    """用户菜单个性化：排序与隐藏。"""

    __tablename__ = "user_menu_prefs"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    config_data: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
