"""公开与系统路由：只做参数解析和响应包装。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import SuperAdmin, ok, require_permission
from app.schemas import EmailSendIn
from app.services.integrations import email as email_service
from app.services.system import site as site_service
from app.services.system import status as status_service

router = APIRouter(tags=["系统"])


@router.get("/health")
async def health():
    return ok({"status": "ok"})


@router.get("/public/site")
async def site_info(db: AsyncSession = Depends(get_db)):
    return ok(await site_service.async_site_info({"session": db}))


@router.get("/system/status")
async def system_status(
    _=Depends(require_permission("system.status")),
    db: AsyncSession = Depends(get_db),
):
    return ok(await status_service.async_status({"session": db}))


@router.post("/admin/email/test")
async def send_test_email(
    body: EmailSendIn, _: SuperAdmin, db: AsyncSession = Depends(get_db)
):
    data = await email_service.async_send_email(
        {
            "session": db,
            "to": body.to,
            "subject": body.subject,
            "content": body.content,
        }
    )
    return ok(data, "邮件已发送")
