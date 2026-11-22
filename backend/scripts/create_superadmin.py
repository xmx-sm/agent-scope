"""创建或提升一个超级管理员。

用途：
- 已有数据库但没有可用超级管理员
- 公开部署时替换默认 MX 账号
- 忘记超级管理员密码时重置

示例：
    ../.venv/bin/python scripts/create_superadmin.py --username admin
    ../.venv/bin/python scripts/create_superadmin.py --username admin --password '强密码'
    ../.venv/bin/python scripts/create_superadmin.py --username MX --promote
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal, init_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import User  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="创建或提升超级管理员")
    parser.add_argument("--username", default=settings.seed_admin_username)
    parser.add_argument("--nickname", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--password", default="")
    parser.add_argument(
        "--promote",
        action="store_true",
        help="同名用户已存在时提升为超级管理员（默认也会提升）",
    )
    parser.add_argument(
        "--no-password-reset",
        action="store_true",
        help="同名用户已存在时保留原密码",
    )
    return parser.parse_args()


async def _main() -> int:
    args = _parse_args()
    username = (args.username or "").strip()
    if not username:
        print("用户名不能为空", file=sys.stderr)
        return 2
    password = args.password
    if not password:
        if sys.stdin.isatty():
            password = getpass.getpass("新密码（至少 6 位，留空表示不重置已有用户）：")
        else:
            password = settings.seed_admin_password
    if password and len(password) < 6:
        print("密码至少 6 位", file=sys.stderr)
        return 2

    await init_db()
    async with AsyncSessionLocal() as session:
        user = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if user is None:
            if not password:
                print("新用户必须提供密码：--password 或交互输入", file=sys.stderr)
                return 2
            user = User(
                username=username,
                nickname=(args.nickname or username).strip(),
                email=(args.email or "").strip() or None,
                role="super_admin",
                password_hash=hash_password(password),
                is_active=True,
            )
            session.add(user)
            await session.commit()
            print(f"已创建超级管理员：{username}")
            return 0

        if not args.no_password_reset and password:
            user.password_hash = hash_password(password)
        if not user.is_active:
            user.is_active = True
        if args.nickname:
            user.nickname = args.nickname.strip()
        if args.email:
            user.email = args.email.strip()
        user.role = "super_admin"
        await session.commit()
        print(f"已提升/更新超级管理员：{username}")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
