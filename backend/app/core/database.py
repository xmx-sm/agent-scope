"""数据库连接与建表。"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """导入全部模型并建表（存量表不会自动补列，新增列需手工 ALTER）。"""
    from app import models  # noqa: F401  确保模型注册到 Base.metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all 不会给存量表补列：这里做已知列的幂等迁移
        if conn.dialect.name == "postgresql":
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar VARCHAR(500)")
            )
            await conn.execute(
                text(
                    "ALTER TABLE menus ADD COLUMN IF NOT EXISTS "
                    "leader_only BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
            await conn.execute(
                text(
                    "ALTER TABLE user_tool_permissions ADD COLUMN IF NOT EXISTS "
                    "require_approval BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
            await conn.execute(
                text(
                    "ALTER TABLE user_tool_permissions ADD COLUMN IF NOT EXISTS "
                    "approval_status VARCHAR(20) NOT NULL DEFAULT 'approved'"
                )
            )


async def close_db() -> None:
    await engine.dispose()
