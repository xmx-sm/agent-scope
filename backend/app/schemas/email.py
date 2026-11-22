"""邮件发送请求模型。"""

from pydantic import BaseModel, Field


class EmailSendIn(BaseModel):
    to: str = Field(min_length=3, max_length=200)
    subject: str = Field(default="Agent Scope 测试邮件", max_length=200)
    content: str = Field(default="这是一封来自 Agent Scope 的测试邮件。", max_length=10000)
