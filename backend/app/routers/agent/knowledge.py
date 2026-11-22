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
    ParseConfigIn,
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
from app.services.agent.conversation import conversations as conv_service
from app.services.agent.resources import mcps as mcp_service
from app.services.agent import knowledge as knowledge_service
from app.services.agent.knowledge import rag as rag_service
from app.services.agent.resources import skills as skill_service
from app.services.agent.resources import subagents as subagent_service
from app.services.agent.collaboration import super_agent as super_service
from app.services.agent.collaboration import a2a as a2a_service
from app.services.agent.automation import scheduled as scheduled_service
from app.services.agent.media import speech as speech_service
from app.services.agent import stats as stats_service
from app.services.agent.conversation import attachments as attachment_service
from app.services.agent.config import user_config as user_config_service
from app.services.tools import tool_config as tool_config_service
from app.services.agent.runtime.stream_manager import resume_events, stream_events
from app.services.config import agent as agent_config_service
from app.utils.mask import SENTINEL



router = APIRouter()


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



@router.get("/knowledge/parse-config")
async def knowledge_parse_config(
    user: CurrentUser, db: AsyncSession = Depends(get_db)
):
    return ok(await knowledge_service.async_parse_config({"session": db}))


@router.put("/knowledge/parse-config")
async def knowledge_set_parse_config(
    body: ParseConfigIn,
    user: SuperAdmin,
    db: AsyncSession = Depends(get_db),
):
    return ok(
        await knowledge_service.async_set_parse_config(
            {
                "session": db,
                "operator_id": user.id,
                "data": body.model_dump(),
            }
        ),
        "解析配置已保存",
    )
