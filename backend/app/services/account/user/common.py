"""用户通用工具：清洗、唯一性校验、登录标识查询。"""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ApiError
from app.models import User


def clean_optional(params: dict) -> str | None:
    """清理可选字符串：去空格，空串转 None。参数：value。"""
    value = params.get("value")
    if value is None:
        return None
    value = str(value).strip()
    return value or None


async def async_assert_unique(params: dict) -> None:
    """校验用户名/邮箱/手机号唯一

    参数：session / username / email / phone / exclude_id
    """
    session: AsyncSession = params["session"]
    username = params.get("username")
    email = params.get("email")
    phone = params.get("phone")
    exclude_id = params.get("exclude_id")
    checks = [
        (User.username, username, "用户名"),
        (User.email, email, "邮箱"),
        (User.phone, phone, "手机号"),
    ]
    for column, value, label in checks:
        if not value:
            continue
        stmt = select(User.id).where(column == value)
        if exclude_id:
            stmt = stmt.where(User.id != exclude_id)
        if (await session.execute(stmt)).first():
            raise ApiError(f"该{label}已被使用")


async def async_find_by_identifier(params: dict) -> User | None:
    """按账号/邮箱/手机号/昵称查找用户

    参数：session / account
    """
    session: AsyncSession = params["session"]
    account = str(params["account"]).strip()
    return (
        await session.execute(
            select(User).where(
                or_(
                    User.username == account,
                    User.nickname == account,
                    User.email == account,
                    User.phone == account,
                )
            )
        )
    ).scalars().first()
