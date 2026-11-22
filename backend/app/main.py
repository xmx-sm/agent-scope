"""FastAPI 应用入口。"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.routers import auth, config, menu, permissions, system, user
from app.core.config import settings
from app.core.database import AsyncSessionLocal, close_db, init_db
from app.core.deps import ApiError
from app.core.seed import async_seed
from app.utils.redis_util import async_close_redis, async_get_redis_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with AsyncSessionLocal() as session:
        await async_seed({"session": session})
    redis = await async_get_redis_client()
    if redis is not None:
        logger.info("Redis 已连接：%s:%s（限流走 Redis）", settings.redis_host, settings.redis_port)
    else:
        logger.warning(
            "Redis 不可用（%s:%s），限流降级为进程内",
            settings.redis_host, settings.redis_port,
        )
    logger.info("后端已启动：%s:%s%s", settings.host, settings.port, settings.api_prefix)
    yield
    await async_close_redis()
    await close_db()


app = FastAPI(title=settings.app_name, version="0.3.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "data": None, "msg": exc.msg},
    )


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "data": None, "msg": str(exc.detail)},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(x) for x in first.get("loc", [])[1:]) or "参数"
    return JSONResponse(
        status_code=200,
        content={"code": 400, "data": None, "msg": f"{field}：{first.get('msg', '参数不合法')}"},
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    logger.warning("数据库唯一约束冲突：%s", exc.orig)
    return JSONResponse(
        status_code=200,
        content={"code": 400, "data": None, "msg": "数据冲突：请检查用户名/邮箱/手机号是否重复"},
    )


for router in (
    system.router,
    auth.router,
    user.router,
    config.router,
    menu.router,
    permissions.router,
):
    app.include_router(router, prefix=settings.api_prefix)
