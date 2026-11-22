"""用户级 Agent 模型配置。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import utc_now


class UserAgentConfig(Base):
    """用户级 Agent 配置（覆盖系统默认）。"""

    __tablename__ = "user_agent_configs"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    use_system_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    base_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    api_key: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)
    context_window: Mapped[int] = mapped_column(Integer, nullable=False, default=131072)
    stream: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    think: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    thinking_budget: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reasoning_effort: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    memory_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    memory_configured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
