"""Agent 对话路由。"""

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import ApiError, CurrentUser, SuperAdmin, ok, require_permission
from app.models import User
from app.schemas import (
    KnowledgeSearchIn,
    LibraryCreateIn,
    LibraryShareIn,
    LibraryUpdateIn,
    SubagentSaveIn,
    SuperAgentSaveIn,
    SuperConversationIn,
    A2APeerIn,
    A2AInvokeIn,
    RagSearchIn,
    ScheduledSaveIn,
    ScheduledToggleIn,
    McpSaveIn,
    ToggleIn,
    ChatStreamIn,
    ConversationBranchIn,
    ConversationCreateIn,
    ConversationRenameIn,
    ModelFetchIn,
    ToolConfigIn,
    TtsIn,
    UserAgentConfigIn,
)
from app.services.agent import conversations as conv_service
from app.services.agent import mcps as mcp_service
from app.services.agent import knowledge as knowledge_service
from app.services.agent import rag as rag_service
from app.services.agent import skills as skill_service
from app.services.agent import subagents as subagent_service
from app.services.agent import super_agent as super_service
from app.services.agent import a2a as a2a_service
from app.services.agent import scheduled as scheduled_service
from app.services.agent import speech as speech_service
from app.services.agent import stats as stats_service
from app.services.agent import attachments as attachment_service
from app.services.agent import user_config as user_config_service
from app.services.tools import tool_config as tool_config_service
from app.services.agent.stream_manager import resume_events, stream_events
from app.services.config import agent as agent_config_service
from app.utils.mask import SENTINEL

router = APIRouter(prefix="/agent", tags=["Agent 对话"])
admin_router = APIRouter(prefix="/admin/agent", tags=["Agent 管理"])


@router.get("/tool-config/{category}")
async def get_tool_config(
    category: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await tool_config_service.async_view(
            {"session": db, "user_id": user.id, "category": category}
        )
    )


@router.put("/tool-config/{category}")
async def save_tool_config(
    category: str, body: ToolConfigIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await tool_config_service.async_save(
            {
                "session": db,
                "user": user,
                "category": category,
                "data": body.model_dump(),
            }
        ),
        "工具配置已保存",
    )


@router.delete("/tool-config/{category}")
async def reset_tool_config(
    category: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await tool_config_service.async_reset(
            {"session": db, "user": user, "category": category}
        ),
        "已恢复系统默认",
    )


@router.post("/tool-config/{category}/test")
async def test_tool_config(
    category: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    if category == "email":
        data = await tool_config_service.async_test_email(
            {"session": db, "user_id": user.id}
        )
    elif category == "db":
        data = await tool_config_service.async_test_db(
            {"session": db, "user_id": user.id}
        )
    else:
        raise ApiError("未知工具配置类别")
    return ok(data, "连接成功")


@admin_router.get("/stats")
async def admin_agent_stats(
    _: SuperAdmin, days: int = 7, db: AsyncSession = Depends(get_db)
):
    return ok(
        await stats_service.async_stats({"session": db, "user_id": None, "days": days})
    )


@router.post("/attachments")
async def upload_attachment(
    user: CurrentUser, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)
):
    return ok(
        await attachment_service.async_upload({"session": db, "user": user, "file": file}),
        "附件已上传",
    )


@router.get("/skills")
async def list_skills(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await skill_service.async_list({"session": db, "user": user}))


@router.post("/skills/upload")
async def upload_skill(
    user: CurrentUser,
    file: UploadFile = File(...),
    name: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    return ok(
        await skill_service.async_upload_zip(
            {
                "session": db,
                "user": user,
                "filename": file.filename or "skill.zip",
                "content": content,
                "name": name,
            }
        ),
        "技能已上传",
    )


@router.patch("/skills/{skill_id}")
async def toggle_skill(
    skill_id: str, body: ToggleIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await skill_service.async_toggle(
            {"session": db, "user": user, "skill_id": skill_id, "is_active": body.is_active}
        )
    )


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)):
    await skill_service.async_delete({"session": db, "user": user, "skill_id": skill_id})
    return ok(None, "技能已删除")


@router.get("/subagents")
async def list_subagents(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await subagent_service.async_list({"session": db, "user": user}))


@router.post("/subagents")
async def save_subagent(
    body: SubagentSaveIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await subagent_service.async_save(
            {"session": db, "user": user, "data": body.model_dump()}
        ),
        "子智能体已保存",
    )


@router.delete("/subagents/{subagent_id}")
async def delete_subagent(
    subagent_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    await subagent_service.async_delete(
        {"session": db, "user": user, "subagent_id": subagent_id}
    )
    return ok(None, "子智能体已删除")


@router.get("/mcps")
async def list_mcps(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await mcp_service.async_list({"session": db, "user": user}))


@router.post("/mcps")
async def save_mcp(
    body: McpSaveIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await mcp_service.async_save({"session": db, "user": user, "data": body.model_dump()}),
        "MCP 已保存",
    )


@router.delete("/mcps/{mcp_id}")
async def delete_mcp(mcp_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)):
    await mcp_service.async_delete({"session": db, "user": user, "mcp_id": mcp_id})
    return ok(None, "MCP 已删除")


@router.get("/knowledge/libraries")
async def knowledge_libraries(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await knowledge_service.async_libraries({"session": db, "user_id": user.id}))


@router.post("/knowledge/libraries")
async def knowledge_library_create(
    body: LibraryCreateIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await knowledge_service.async_library_create(
            {"session": db, "user_id": user.id, "data": body.model_dump()}
        ),
        "向量库已创建",
    )


@router.put("/knowledge/libraries/{library_id}")
async def knowledge_library_update(
    library_id: str, body: LibraryUpdateIn, user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    return ok(
        await knowledge_service.async_library_update(
            {"session": db, "user_id": user.id, "library_id": library_id,
             "data": body.model_dump(exclude_unset=True)}
        ),
        "向量库已更新",
    )


@router.delete("/knowledge/libraries/{library_id}")
async def knowledge_library_delete(
    library_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    await knowledge_service.async_library_delete(
        {"session": db, "user_id": user.id, "library_id": library_id}
    )
    return ok(None, "向量库已删除")


@router.post("/knowledge/libraries/{library_id}/rebuild")
async def knowledge_library_rebuild(
    library_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await knowledge_service.async_library_rebuild(
            {"session": db, "user_id": user.id, "library_id": library_id}
        ),
        "索引已重建",
    )


@router.post("/knowledge/libraries/{library_id}/test")
async def knowledge_library_test(
    library_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await knowledge_service.async_library_test(
            {"session": db, "user_id": user.id, "library_id": library_id}
        ),
        "连接成功",
    )


@router.get("/knowledge/documents")
async def knowledge_documents(
    user: CurrentUser, library_id: str = "", status: str = "",
    db: AsyncSession = Depends(get_db),
):
    return ok(
        await knowledge_service.async_documents(
            {"session": db, "user_id": user.id, "library_id": library_id, "status": status}
        )
    )


@router.post("/knowledge/documents/upload")
async def knowledge_document_upload(
    user: CurrentUser,
    file: UploadFile = File(...),
    library_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    return ok(
        await knowledge_service.async_upload_document(
            {"session": db, "user_id": user.id, "library_id": library_id,
             "filename": file.filename or "file", "content": content}
        ),
        "文档已上传",
    )


@router.post("/knowledge/documents/{document_id}/parse")
async def knowledge_document_parse(
    document_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await knowledge_service.async_parse_document(
            {"session": db, "user_id": user.id, "document_id": document_id}
        ),
        "文档已解析",
    )


@router.delete("/knowledge/documents/{document_id}")
async def knowledge_document_delete(
    document_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    await knowledge_service.async_delete_document(
        {"session": db, "user_id": user.id, "document_id": document_id}
    )
    return ok(None, "文档已删除")


@router.post("/knowledge/search")
async def knowledge_search(
    body: KnowledgeSearchIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await knowledge_service.async_search(
            {
                "session": db,
                "user_id": user.id,
                "query": body.query,
                "library_ids": body.library_ids,
                "top_k": body.top_k,
                "score_threshold": body.score_threshold,
            }
        )
    )


@router.get("/knowledge/logs")
async def knowledge_logs(
    user: CurrentUser, library_id: str = "", db: AsyncSession = Depends(get_db)
):
    return ok(
        await knowledge_service.async_logs(
            {"session": db, "user_id": user.id, "library_id": library_id}
        )
    )


@router.get("/rag/libraries")
async def rag_libraries(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await rag_service.async_libraries({"session": db, "user_id": user.id}))


@router.get("/rag/documents")
async def rag_documents(
    user: CurrentUser, collection: str = "default", db: AsyncSession = Depends(get_db)
):
    return ok(
        await rag_service.async_documents(
            {"session": db, "user_id": user.id, "collection": collection}
        )
    )


@router.post("/rag/upload")
async def rag_upload(
    user: CurrentUser,
    file: UploadFile = File(...),
    collection: str = Form("default"),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    return ok(
        await rag_service.async_upload(
            {
                "session": db,
                "user_id": user.id,
                "collection": collection,
                "filename": file.filename or "file",
                "content": content,
            }
        ),
        "文档已入库",
    )


@router.post("/rag/search")
async def rag_search(
    body: RagSearchIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await rag_service.async_search(
            {
                "session": db,
                "user_id": user.id,
                "collection": body.collection,
                "query": body.query,
                "top_k": body.top_k,
            }
        )
    )


@router.delete("/rag/documents")
async def rag_delete_document(
    user: CurrentUser,
    doc_id: str,
    collection: str = "default",
    db: AsyncSession = Depends(get_db),
):
    return ok(
        await rag_service.async_delete_document(
            {
                "session": db,
                "user_id": user.id,
                "collection": collection,
                "doc_id": doc_id,
            }
        ),
        "文档已删除",
    )


@router.delete("/rag/libraries/{collection}")
async def rag_delete_library(
    collection: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await rag_service.async_delete_library(
            {"session": db, "user_id": user.id, "collection": collection}
        ),
        "知识库已删除",
    )


@router.get("/providers")
async def user_providers(_: CurrentUser):
    return ok(agent_config_service.PROVIDERS)


@router.get("/config")
async def get_agent_config(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await user_config_service.async_view({"session": db, "user": user}))


@router.put("/config")
async def save_agent_config(
    body: UserAgentConfigIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await user_config_service.async_save(
            {"session": db, "user": user, "data": body.model_dump()}
        ),
        "Agent 配置已保存",
    )


@router.delete("/config")
async def reset_agent_config(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(
        await user_config_service.async_reset({"session": db, "user": user}),
        "已恢复跟随系统默认",
    )


@router.post("/models")
async def fetch_user_models(
    body: ModelFetchIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    effective = await user_config_service.async_effective({"session": db, "user": user})
    api_key = body.api_key
    if not api_key or api_key == SENTINEL:
        api_key = str(effective.get("api_key") or "")
    base_url = body.base_url or str(effective.get("base_url") or "")
    provider = body.provider or str(effective.get("provider") or "")
    return ok(
        await agent_config_service.async_fetch_models(
            {
                "provider": provider,
                "base_url": base_url,
                "api_key": api_key,
            }
        ),
        "模型列表已获取",
    )


@router.get("/stats")
async def agent_stats(
    user: CurrentUser, days: int = 7, db: AsyncSession = Depends(get_db)
):
    return ok(
        await stats_service.async_stats(
            {"session": db, "user_id": user.id, "days": days}
        )
    )


@router.get("/conversations")
async def list_conversations(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await conv_service.async_list_conversations({"session": db, "user_id": user.id}))


@router.post("/conversations")
async def create_conversation(
    body: ConversationCreateIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await conv_service.async_create_conversation(
            {"session": db, "user_id": user.id, "title": body.title}
        ),
        "会话已创建",
    )


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    body: ConversationRenameIn,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    return ok(
        await conv_service.async_rename_conversation(
            {"session": db, "user_id": user.id, "conversation_id": conversation_id,
             "title": body.title}
        ),
        "会话已重命名",
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    await conv_service.async_delete_conversation(
        {"session": db, "user_id": user.id, "conversation_id": conversation_id}
    )
    return ok(None, "会话已删除")


@router.post("/conversations/{conversation_id}/branch")
async def branch_conversation(
    conversation_id: str,
    body: ConversationBranchIn,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    return ok(
        await conv_service.async_branch_conversation(
            {
                "session": db,
                "user_id": user.id,
                "conversation_id": conversation_id,
                "message_id": body.message_id,
            }
        ),
        "分支已创建",
    )


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await conv_service.async_list_messages(
            {"session": db, "user_id": user.id, "conversation_id": conversation_id}
        )
    )


@router.get("/chat/resume/{conversation_id}")
async def chat_resume(
    conversation_id: str,
    user: User = Depends(require_permission("ai.use")),
):
    return StreamingResponse(
        resume_events(user.id, conversation_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/chat/stream")
async def chat_stream(
    body: ChatStreamIn,
    user: User = Depends(require_permission("ai.use")),
):
    return StreamingResponse(
        stream_events(
            user.id, body.conversation_id, body.content, body.attachment_ids
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ==================== 超级智能体 ====================

@router.get("/super-agent")
async def super_agent_get(
    user: CurrentUser, super_agent_id: str = "", db: AsyncSession = Depends(get_db)
):
    return ok(
        await super_service.async_get(
            {"session": db, "user_id": user.id, "super_agent_id": super_agent_id or None}
        )
    )


@router.get("/super-agents")
async def super_agent_list(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await super_service.async_list({"session": db, "user_id": user.id}))


@router.post("/super-agent")
async def super_agent_save(
    body: SuperAgentSaveIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await super_service.async_save(
            {"session": db, "user_id": user.id, "data": body.model_dump()}
        ),
        "超级智能体已保存",
    )


@router.delete("/super-agent")
async def super_agent_delete(
    user: CurrentUser, super_agent_id: str = "", db: AsyncSession = Depends(get_db)
):
    await super_service.async_delete(
        {"session": db, "user_id": user.id, "super_agent_id": super_agent_id or None}
    )
    return ok(None, "已删除")


@router.post("/super-agent/main-conversation")
async def super_main_conversation(
    body: SuperConversationIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await super_service.async_create_conversation(
            {
                "session": db,
                "user_id": user.id,
                "super_agent_id": body.super_agent_id,
                "member_id": body.member_id,
                "role": body.role,
                "title": body.title,
            }
        ),
        "主会话已创建",
    )


@router.post("/super-agent/conversation")
async def super_member_conversation(
    body: SuperConversationIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await super_service.async_create_conversation(
            {
                "session": db,
                "user_id": user.id,
                "super_agent_id": body.super_agent_id,
                "member_id": body.member_id,
                "role": body.role,
                "title": body.title,
            }
        ),
        "会话已创建",
    )


# ==================== A2A 管理面 ====================

@router.get("/a2a/peers")
async def a2a_peers(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await a2a_service.async_list_peers({"session": db, "user": user}))


@router.post("/a2a/peers")
async def a2a_peer_save(
    body: A2APeerIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await a2a_service.async_save_peer(
            {"session": db, "user": user, "data": body.model_dump()}
        ),
        "伙伴已保存",
    )


@router.delete("/a2a/peers/{peer_id}")
async def a2a_peer_delete(
    peer_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    await a2a_service.async_delete_peer({"session": db, "user": user, "peer_id": peer_id})
    return ok(None, "已删除")


@router.post("/a2a/peers/{peer_id}/rotate")
async def a2a_peer_rotate(
    peer_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await a2a_service.async_rotate_key({"session": db, "user": user, "peer_id": peer_id}),
        "密钥已重置",
    )


@router.get("/a2a/peers/{peer_id}/key")
async def a2a_peer_key(
    peer_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await a2a_service.async_reveal_key({"session": db, "user": user, "peer_id": peer_id})
    )


@router.post("/a2a/peers/{peer_id}/test")
async def a2a_peer_test(
    peer_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await a2a_service.async_test_peer({"session": db, "user": user, "peer_id": peer_id}),
        "连接成功",
    )


@router.post("/a2a/invoke")
async def a2a_invoke(
    body: A2AInvokeIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await a2a_service.async_invoke_peer(
            {
                "session": db,
                "user": user,
                "peer": body.peer,
                "message": body.message,
                "session_hint": body.session_hint,
            }
        )
    )


@router.get("/a2a/invocations")
async def a2a_invocations(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await a2a_service.async_invocations({"session": db, "user": user}))


@router.get("/knowledge/share-candidates")
async def knowledge_share_candidates(
    user: CurrentUser, q: str = "", db: AsyncSession = Depends(get_db)
):
    return ok(
        await knowledge_service.async_share_candidates(
            {"session": db, "user_id": user.id, "q": q}
        )
    )


@router.get("/knowledge/libraries/{library_id}/shares")
async def knowledge_shares(
    library_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await knowledge_service.async_shares(
            {"session": db, "user_id": user.id, "library_id": library_id}
        )
    )


@router.post("/knowledge/libraries/{library_id}/shares")
async def knowledge_share_add(
    library_id: str,
    body: LibraryShareIn,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    return ok(
        await knowledge_service.async_share_add(
            {
                "session": db,
                "user_id": user.id,
                "library_id": library_id,
                "target_user_id": body.target_user_id,
                "permission": body.permission,
            }
        ),
        "已共享",
    )


@router.delete("/knowledge/libraries/{library_id}/shares/{target_user_id}")
async def knowledge_share_remove(
    library_id: str,
    target_user_id: str,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    await knowledge_service.async_share_remove(
        {
            "session": db,
            "user_id": user.id,
            "library_id": library_id,
            "target_user_id": target_user_id,
        }
    )
    return ok(None, "已取消共享")


@router.post("/knowledge/libraries/{library_id}/parse-pending")
async def knowledge_parse_pending(
    library_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await knowledge_service.async_parse_pending(
            {"session": db, "user_id": user.id, "library_id": library_id}
        ),
        "批量解析完成",
    )


@router.get("/knowledge/documents/{document_id}/chunks")
async def knowledge_document_chunks(
    document_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await knowledge_service.async_chunks(
            {"session": db, "user_id": user.id, "document_id": document_id}
        )
    )


@router.get("/knowledge/documents/{document_id}/download")
async def knowledge_document_download(
    document_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    path, filename = await knowledge_service.async_document_file(
        {"session": db, "user_id": user.id, "document_id": document_id}
    )
    return FileResponse(path, filename=filename)


# ==================== 定时任务 ====================

@router.get("/scheduled-jobs")
async def scheduled_list(user: CurrentUser, db: AsyncSession = Depends(get_db)):
    return ok(await scheduled_service.async_list({"session": db, "user_id": user.id}))


@router.post("/scheduled-jobs")
async def scheduled_save(
    body: ScheduledSaveIn, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await scheduled_service.async_save(
            {"session": db, "user_id": user.id, "data": body.model_dump()}
        ),
        "定时任务已保存",
    )


@router.post("/scheduled-jobs/{job_id}/toggle")
async def scheduled_toggle(
    job_id: str,
    body: ScheduledToggleIn,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    return ok(
        await scheduled_service.async_toggle(
            {
                "session": db,
                "user_id": user.id,
                "job_id": job_id,
                "enabled": body.enabled,
            }
        )
    )


@router.post("/scheduled-jobs/{job_id}/run-now")
async def scheduled_run_now(
    job_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(
        await scheduled_service.async_run_now(
            {"session": db, "user_id": user.id, "job_id": job_id}
        ),
        "已提交执行",
    )


@router.delete("/scheduled-jobs/{job_id}")
async def scheduled_delete(
    job_id: str, user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    await scheduled_service.async_delete(
        {"session": db, "user_id": user.id, "job_id": job_id}
    )
    return ok(None, "已删除")


@router.post("/tts")
async def agent_tts(body: TtsIn, user: CurrentUser, db: AsyncSession = Depends(get_db)):
    result = await speech_service.async_synthesize(
        {"session": db, "text": body.text, "voice": body.voice, "model": body.model}
    )
    return Response(
        content=result["audio"],
        media_type=result["media_type"],
        headers={"X-Tts-Bytes": str(result["bytes"])},
    )
