"""安全策略请求模型。"""

from pydantic import BaseModel


class DbAccessCheckIn(BaseModel):
    database: str = ""
    table: str = ""
