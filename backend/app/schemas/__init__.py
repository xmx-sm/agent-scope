"""请求模型统一出口。"""

from app.schemas.agent import (
    A2AInboundIn,
    A2AInvokeIn,
    A2APeerIn,
    ChatStreamIn,
    ConversationBranchIn,
    ConversationCreateIn,
    ConversationRenameIn,
    KnowledgeSearchIn,
    LibraryCreateIn,
    LibraryShareIn,
    LibraryUpdateIn,
    McpSaveIn,
    ModelFetchIn,
    ParseConfigIn,
    RagSearchIn,
    ScheduledSaveIn,
    ScheduledToggleIn,
    SubagentSaveIn,
    SuperAgentSaveIn,
    SuperConversationIn,
    ToggleIn,
    TtsIn,
    UserAgentConfigIn,
)
from app.schemas.auth import ChangePasswordIn, LoginIn, RefreshIn, RegisterIn
from app.schemas.config import ConfigUpdateIn
from app.schemas.email import EmailSendIn
from app.schemas.menu import MenuCreateIn, MenuPrefIn, MenuReorderIn, MenuUpdateIn
from app.schemas.permission import PermissionUpdateIn, TempGrantIn, UserPermissionUpdateIn
from app.schemas.security import DbAccessCheckIn
from app.schemas.tool import ToolItemIn, ToolNarrowIn, ToolPolicyIn, ToolSetIn
from app.schemas.tool_approval import (
    ToolApprovalDecisionIn,
    ToolApprovalRequestIn,
    ToolApprovalRequiredIn,
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
    "ParseConfigIn",
    "KnowledgeSearchIn",
    "RagSearchIn",
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
    "ToolApprovalRequestIn",
    "ToolApprovalDecisionIn",
    "ToolApprovalRequiredIn",
    "ToolPolicyIn",
    "DbAccessCheckIn",
    "SuperAgentSaveIn",
    "SuperConversationIn",
    "A2APeerIn",
    "A2AInvokeIn",
    "A2AInboundIn",
    "ScheduledSaveIn",
    "ScheduledToggleIn",
]
