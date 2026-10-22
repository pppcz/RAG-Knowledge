"""注册、登录、租户内用户管理业务逻辑。"""

import re
import secrets
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    RegisterRequest,
    TokenResponse,
    UserCreateRequest,
    UserOut,
)
from app.services import rbac


def slugify_tenant(name: str) -> str:
    """租户名转 slug；纯中文等非 ASCII 名称退化为随机标识。"""
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug[:48] if slug else f"tenant-{secrets.token_hex(3)}"


async def _unique_tenant_slug(session: AsyncSession, base: str) -> str:
    """生成未被占用的租户标识。"""
    candidate = base[:56]
    for _ in range(5):
        if await session.scalar(select(Tenant.id).where(Tenant.slug == candidate)) is None:
            return candidate
        candidate = f"{base[:48]}-{secrets.token_hex(3)}"
    raise AppError(40901, "无法生成唯一租户标识，请显式指定 tenant_slug", 409)


def _build_token_response(user: User, role_codes: list[str]) -> TokenResponse:
    """签发令牌并组装响应。"""
    token = create_access_token(
        subject=str(user.id),
        tenant_id=user.tenant_id,
        roles=role_codes,
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserOut.model_validate(user),
    )


async def register_tenant(session: AsyncSession, payload: RegisterRequest) -> TokenResponse:
    """注册租户并创建该租户的管理员账号。"""
    if payload.tenant_slug:
        if await session.scalar(select(Tenant.id).where(Tenant.slug == payload.tenant_slug)):
            raise AppError(
                40901,
                f"租户标识已存在：{payload.tenant_slug}",
                409,
                {"field": "tenant_slug"},
            )
        slug = payload.tenant_slug
    else:
        slug = await _unique_tenant_slug(session, slugify_tenant(payload.tenant_name))

    tenant = Tenant(name=payload.tenant_name, slug=slug, is_active=True)
    session.add(tenant)
    await session.flush()

    roles = await rbac.ensure_tenant_roles(session, tenant.id)

    user = User(
        tenant_id=tenant.id,
        username=payload.username,
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        is_active=True,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            40901,
            "该租户内用户名或邮箱已被占用",
            409,
        ) from exc

    await rbac.assign_roles(session, user.id, [roles["admin"].id])
    await session.commit()

    role_codes = await rbac.get_role_codes(session, user.id)
    return _build_token_response(user, role_codes)


async def authenticate(session: AsyncSession, payload: LoginRequest) -> TokenResponse:
    """校验用户名 / 密码并签发令牌。"""
    stmt = select(User).where(User.username == payload.username, User.deleted_at.is_(None))
    if payload.tenant_slug:
        stmt = stmt.join(Tenant, Tenant.id == User.tenant_id).where(
            Tenant.slug == payload.tenant_slug
        )

    candidates = list((await session.execute(stmt)).scalars())
    if not candidates:
        raise AppError(40101, "用户名或密码错误", 401)
    if len(candidates) > 1:
        raise AppError(
            40001,
            "该用户名存在于多个租户，请提供 tenant_slug",
            400,
            {"matches": len(candidates)},
        )

    user = candidates[0]
    if not user.is_active:
        raise AppError(40301, "账号已停用", 403)
    if not verify_password(payload.password, user.password_hash):
        raise AppError(40101, "用户名或密码错误", 401)

    role_codes = await rbac.get_role_codes(session, user.id)
    return _build_token_response(user, role_codes)


async def build_me(session: AsyncSession, user: User) -> MeResponse:
    """当前用户 + 角色 + 权限。"""
    return MeResponse(
        user=UserOut.model_validate(user),
        roles=await rbac.get_role_codes(session, user.id),
        permissions=await rbac.get_permission_codes(session, user.id),
    )


async def create_tenant_user(
    session: AsyncSession,
    tenant_id: int,
    payload: UserCreateRequest,
) -> UserOut:
    """在指定租户内创建用户（调用方需已通过 users:write 校验）。"""
    duplicate = await session.scalar(
        select(User.id).where(
            User.tenant_id == tenant_id,
            User.username == payload.username,
            User.deleted_at.is_(None),
        )
    )
    if duplicate is not None:
        raise AppError(40901, f"用户名已存在：{payload.username}", 409, {"field": "username"})

    email = str(payload.email).lower()
    duplicate_email = await session.scalar(
        select(User.id).where(
            User.tenant_id == tenant_id,
            User.email == email,
            User.deleted_at.is_(None),
        )
    )
    if duplicate_email is not None:
        raise AppError(40901, f"邮箱已存在：{email}", 409, {"field": "email"})

    roles = await rbac.get_role_by_codes(session, tenant_id, payload.role_codes or ["member"])

    user = User(
        tenant_id=tenant_id,
        username=payload.username,
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    await rbac.assign_roles(session, user.id, [role.id for role in roles])
    await session.commit()
    return UserOut.model_validate(user)


async def list_tenant_users(
    session: AsyncSession,
    tenant_id: int,
    page: int,
    page_size: int,
) -> tuple[list[User], int]:
    """分页查询租户内用户，强制 tenant_id 过滤。"""
    condition = (User.tenant_id == tenant_id, User.deleted_at.is_(None))

    total = (await session.scalar(select(func.count()).select_from(User).where(*condition))) or 0

    users = list(
        (
            await session.execute(
                select(User)
                .where(*condition)
                .order_by(User.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars()
    )
    return users, total
