"""AI 工具审批请求模型。"""

from pydantic import BaseModel, Field


class ToolApprovalRequestIn(BaseModel):
    group: str
    tool: str = ""
    reason: str = Field(default="", max_length=1000)


class ToolApprovalDecisionIn(BaseModel):
    approve: bool


class ToolApprovalRequiredIn(BaseModel):
    group: str
    tool: str = ""
    require_approval: bool = True
