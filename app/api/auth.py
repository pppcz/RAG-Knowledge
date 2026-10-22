"""鉴权与用户管理接口。"""

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, SessionDep, require_permission
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    MeResponse,
    RegisterRequest,
    TokenResponse,
    UserCreateRequest,
    UserOut,
)
from app.schemas.common import ErrorResponse, Page, PaginationParams
from app.services import auth as auth_service

router = APIRouter()

COMMON_ERRORS = {
    400: {"model": ErrorResponse, "description": "参数或业务错误"},
    401: {"model": ErrorResponse, "description": "未认证 / 令牌无效"},
    403: {"model": ErrorResponse, "description": "权限不足"},
    409: {"model": ErrorResponse, "description": "资源冲突"},
}


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="注册租户与管理员",
    description=(
        "创建一个新租户，并在该租户下创建管理员账号（admin 角色，拥有全部权限）。"
        "返回的 access_token 可直接用于后续接口。"
    ),
    responses={409: {"model": ErrorResponse, "description": "租户标识已存在"}},
)
async def register(payload: RegisterRequest, session: SessionDep) -> TokenResponse:
    """注册：创建租户 + 管理员用户 + 默认角色。"""
    return await auth_service.register_tenant(session, payload)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="登录获取 JWT",
    description=(
        "使用用户名与密码登录。用户名在租户内唯一；若同一用户名存在于多个租户，"
        "必须额外提供 tenant_slug 以消除歧义。"
    ),
    responses=COMMON_ERRORS,
)
async def login(payload: LoginRequest, session: SessionDep) -> TokenResponse:
    """登录并签发 JWT。"""
    return await auth_service.authenticate(session, payload)


@router.get(
    "/me",
    response_model=MeResponse,
    summary="当前用户信息",
    description="返回当前登录用户及其角色编码、权限编码列表。",
    responses={401: {"model": ErrorResponse, "description": "未认证 / 令牌无效"}},
)
async def me(session: SessionDep, current_user: CurrentUser) -> MeResponse:
    """当前用户 + 角色 + 权限。"""
    return await auth_service.build_me(session, current_user)


@router.get(
    "/users",
    response_model=Page[UserOut],
    summary="租户内用户列表",
    description="分页返回当前租户的用户，强制按 tenant_id 隔离；需要 users:read 权限。",
    responses=COMMON_ERRORS,
)
async def list_users(
    session: SessionDep,
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(require_permission("users:read")),
) -> Page[UserOut]:
    """分页列出当前租户用户。"""
    users, total = await auth_service.list_tenant_users(
        session,
        tenant_id=current_user.tenant_id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return Page[UserOut](
        items=[UserOut.model_validate(user) for user in users],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="创建租户内用户",
    description="在当前租户下创建用户并分配角色，需要 users:write 权限。",
    responses=COMMON_ERRORS,
)
async def create_user(
    payload: UserCreateRequest,
    session: SessionDep,
    current_user: User = Depends(require_permission("users:write")),
) -> UserOut:
    """创建用户（租户隔离）。"""
    return await auth_service.create_tenant_user(session, current_user.tenant_id, payload)
