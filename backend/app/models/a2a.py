"""A2A 伙伴、调用留痕与会话映射。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import new_id, utc_now


class A2APeer(Base):
    __tablename__ = "a2a_peers"
    __table_args__ = (UniqueConstraint("owner_user_id", "name", name="uq_a2a_owner_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    endpoint: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    api_key: Mapped[str] = mapped_column(String(200), nullable=False, default="", index=True)
    remote_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    direction: Mapped[str] = mapped_column(String(20), nullable=False, default="outbound")
    protocol: Mapped[str] = mapped_column(String(20), nullable=False, default="lite")
    allow_tools: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_calls_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class A2AInvocation(Base):
    __tablename__ = "a2a_invocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    peer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("a2a_peers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(10), nullable=False, default="out")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    response: Mapped[str] = mapped_column(Text, nullable=False, default="")
    elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class A2ASessionMap(Base):
    __tablename__ = "a2a_session_maps"
    __table_args__ = (
        UniqueConstraint("peer_id", "session_hint", name="uq_a2a_peer_session"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    peer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("a2a_peers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_hint: Mapped[str] = mapped_column(String(200), nullable=False, default="default")
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
