"""定时任务请求模型。"""

from pydantic import BaseModel


class ScheduledSaveIn(BaseModel):
    id: str | None = None
    name: str
    instruction: str
    interval_seconds: int = 3600
    schedule_mode: str = "interval"
    calendar_rule: dict | None = None
    conv_mode: str = "new"
    conversation_id: str | None = None
    timeout_seconds: int = 300
    enabled: bool = True


class ScheduledToggleIn(BaseModel):
    enabled: bool
