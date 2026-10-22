"""初始化默认租户与管理员账号（幂等）。

用法（项目根目录执行）：

    uv run python -m scripts.seed
    uv run python -m scripts.seed --username admin --password 123456 --tenant default

默认凭据仅用于本地开发，生产环境请立即修改。
"""

import argparse
import logging

from app.core import asyncio_compat
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User
from app.services import rbac
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def seed(
    tenant_slug: str,
    tenant_name: str,
    username: str,
    password: str,
    email: str,
) -> None:
    """创建（或补齐）默认租户与管理员用户。"""
    async with SessionLocal() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
        if tenant is None:
            tenant = Tenant(name=tenant_name, slug=tenant_slug, description="系统默认租户")
            session.add(tenant)
            await session.flush()
            logger.info("创建租户 %s (id=%s)", tenant_slug, tenant.id)
        else:
            logger.info("租户已存在 %s (id=%s)", tenant_slug, tenant.id)

        roles = await rbac.ensure_tenant_roles(session, tenant.id)

        user = await session.scalar(
            select(User).where(User.tenant_id == tenant.id, User.username == username)
        )
        if user is None:
            user = User(
                tenant_id=tenant.id,
                username=username,
                email=email.lower(),
                password_hash=hash_password(password),
                full_name="系统管理员",
                is_active=True,
                is_superuser=False,
            )
            session.add(user)
            await session.flush()
            logger.info("创建用户 %s (id=%s)", username, user.id)
        else:
            logger.info("用户已存在 %s (id=%s)，未修改密码", username, user.id)

        await rbac.assign_roles(session, user.id, [roles["admin"].id])
        await session.commit()
        logger.info(
            "完成：tenant=%s user=%s 角色=admin 权限=%s",
            tenant_slug,
            username,
            await rbac.get_permission_codes(session, user.id),
        )


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="初始化默认租户与管理员账号")
    parser.add_argument("--tenant", default="default", help="租户 slug")
    parser.add_argument("--tenant-name", default="默认租户", help="租户名称")
    parser.add_argument("--username", default="admin", help="管理员用户名")
    parser.add_argument("--password", default="123456", help="管理员密码（仅本地开发）")
    parser.add_argument("--email", default="admin@example.com", help="管理员邮箱")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio_compat.run(
        seed(
            tenant_slug=args.tenant,
            tenant_name=args.tenant_name,
            username=args.username,
            password=args.password,
            email=args.email,
        )
    )


if __name__ == "__main__":
    main()
