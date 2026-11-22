"""Agent 领域请求模型统一出口。"""

from app.schemas.agent.automation import ScheduledSaveIn, ScheduledToggleIn
from app.schemas.agent.chat import ChatStreamIn, ConversationCreateIn, TtsIn
from app.schemas.agent.collaboration import (
    A2AInboundIn,
    A2AInvokeIn,
    A2APeerIn,
    SuperAgentSaveIn,
    SuperConversationIn,
)
from app.schemas.agent.config import ModelFetchIn, UserAgentConfigIn
from app.schemas.agent.conversation import ConversationBranchIn, ConversationRenameIn
from app.schemas.agent.knowledge import (
    KnowledgeSearchIn,
    LibraryCreateIn,
    LibraryShareIn,
    LibraryUpdateIn,
    ParseConfigIn,
    RagSearchIn,
)
from app.schemas.agent.resources import McpSaveIn, SubagentSaveIn, ToggleIn

__all__ = [
    "ChatStreamIn",
    "ConversationCreateIn",
    "TtsIn",
    "ConversationRenameIn",
    "ConversationBranchIn",
    "ModelFetchIn",
    "UserAgentConfigIn",
    "KnowledgeSearchIn",
    "LibraryCreateIn",
    "LibraryUpdateIn",
    "LibraryShareIn",
    "ParseConfigIn",
    "RagSearchIn",
    "McpSaveIn",
    "SubagentSaveIn",
    "ToggleIn",
    "SuperAgentSaveIn",
    "SuperConversationIn",
    "A2APeerIn",
    "A2AInvokeIn",
    "A2AInboundIn",
    "ScheduledSaveIn",
    "ScheduledToggleIn",
]
