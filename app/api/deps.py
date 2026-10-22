"""FastAPI 依赖：数据库会话、当前用户、RBAC 权限校验。"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.errors import AppError
from app.core.security import TokenExpiredError, TokenInvalidError, decode_access_token
from app.models.user import User
from app.services import rbac

bearer_scheme = HTTPBearer(auto_error=False, description="Authorization: Bearer <token>")

SessionDep = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User:
    """解析 Bearer Token 并加载用户，校验租户与 Token 一致。"""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppError(40101, "未提供访问令牌", 401)

    try:
        payload = decode_access_token(credentials.credentials)
    except TokenExpiredError as exc:
        raise AppError(40102, str(exc), 401) from exc
    except TokenInvalidError as exc:
        raise AppError(40101, str(exc), 401) from exc

    subject = payload.get("sub")
    tenant_id = payload.get("tid")
    if not isinstance(subject, str) or not isinstance(tenant_id, int):
        raise AppError(40101, "访问令牌缺少必要声明", 401)

    try:
        user_id = int(subject)
    except ValueError as exc:
        raise AppError(40101, "访问令牌主体无效", 401) from exc

    user = await session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise AppError(40101, "用户不存在或已删除", 401)
    if user.tenant_id != tenant_id:
        raise AppError(40101, "令牌与用户所属租户不匹配", 401)
    if not user.is_active:
        raise AppError(40301, "账号已停用", 403)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(permission_code: str):
    """生成 RBAC 权限校验依赖。"""

    async def checker(session: SessionDep, user: CurrentUser) -> User:
        if user.is_superuser:
            return user
        permission_codes = set(await rbac.get_permission_codes(session, user.id))
        if permission_code not in permission_codes:
            raise AppError(
                40301,
                f"缺少权限：{permission_code}",
                403,
                {"required_permission": permission_code},
            )
        return user

    return checker
