"""请求模型统一出口。"""

from app.schemas.agent import ModelFetchIn, UserAgentConfigIn
from app.schemas.auth import ChangePasswordIn, LoginIn, RefreshIn, RegisterIn
from app.schemas.chat import ChatStreamIn, ConversationCreateIn, TtsIn
from app.schemas.conversation import ConversationBranchIn, ConversationRenameIn
from app.schemas.config import ConfigUpdateIn
from app.schemas.email import EmailSendIn
from app.schemas.knowledge import (
    KnowledgeSearchIn,
    LibraryCreateIn,
    LibraryShareIn,
    LibraryUpdateIn,
)
from app.schemas.menu import MenuCreateIn, MenuPrefIn, MenuReorderIn, MenuUpdateIn
from app.schemas.permission import PermissionUpdateIn, TempGrantIn, UserPermissionUpdateIn
from app.schemas.rag import RagSearchIn
from app.schemas.scheduled import ScheduledSaveIn, ScheduledToggleIn
from app.schemas.security import DbAccessCheckIn
from app.schemas.tool import ToolItemIn, ToolNarrowIn, ToolPolicyIn, ToolSetIn
from app.schemas.tool_approval import (
    ToolApprovalDecisionIn,
    ToolApprovalRequestIn,
    ToolApprovalRequiredIn,
)
from app.schemas.skill import McpSaveIn, ToggleIn
from app.schemas.subagent import SubagentSaveIn
from app.schemas.super_agent import (
    A2AInvokeIn,
    A2AInboundIn,
    A2APeerIn,
    SuperAgentSaveIn,
    SuperConversationIn,
)
from app.schemas.tool_config import ToolConfigIn
from app.schemas.user import ProfileUpdateIn, ResetPasswordIn, UserCreateIn, UserUpdateIn

__all__ = [
    "RegisterIn",
    "ModelFetchIn",
    "UserAgentConfigIn",
    "LoginIn",
    "RefreshIn",
    "ChangePasswordIn",
    "ProfileUpdateIn",
    "UserCreateIn",
    "UserUpdateIn",
    "ResetPasswordIn",
    "ConfigUpdateIn",
    "ConversationCreateIn",
    "ConversationRenameIn",
    "ConversationBranchIn",
    "ChatStreamIn",
    "TtsIn",
    "EmailSendIn",
    "MenuCreateIn",
    "MenuUpdateIn",
    "MenuReorderIn",
    "MenuPrefIn",
    "LibraryCreateIn",
    "LibraryUpdateIn",
    "LibraryShareIn",
    "KnowledgeSearchIn",
    "PermissionUpdateIn",
    "TempGrantIn",
    "UserPermissionUpdateIn",
    "ToolItemIn",
    "ToolSetIn",
    "ToolNarrowIn",
    "ToolConfigIn",
    "ToggleIn",
    "McpSaveIn",
    "SubagentSaveIn",
    "SuperAgentSaveIn",
    "SuperConversationIn",
    "A2APeerIn",
    "A2AInvokeIn",
    "A2AInboundIn",
    "ToolApprovalRequestIn",
    "ToolApprovalDecisionIn",
    "ToolApprovalRequiredIn",
    "ToolPolicyIn",
    "DbAccessCheckIn",
    "RagSearchIn",
    "ScheduledSaveIn",
    "ScheduledToggleIn",
]
