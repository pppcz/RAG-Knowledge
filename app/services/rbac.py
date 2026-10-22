"""RBAC：权限目录、默认角色、用户权限查询。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.user import Permission, Role, RolePermission, UserRole

# 全局权限目录（code, 名称, 说明）
PERMISSION_CATALOG: list[tuple[str, str, str]] = [
    ("users:read", "查看用户", "查看本租户用户列表"),
    ("users:write", "管理用户", "创建 / 停用本租户用户"),
    ("kb:read", "查看知识库", "查看知识库列表与详情"),
    ("kb:write", "管理知识库", "创建 / 修改 / 删除知识库"),
    ("docs:read", "查看文档", "查看文档列表与切片"),
    ("docs:write", "管理文档", "上传 / 删除 / 重建文档索引"),
    ("chat:ask", "知识库问答", "发起 RAG 问答与会话"),
]

# 租户默认角色：admin 拥有全部权限，member 只读 + 问答
ROLE_SPECS: dict[str, tuple[str, list[str]]] = {
    "admin": ("租户管理员", [code for code, _, _ in PERMISSION_CATALOG]),
    "member": ("普通成员", ["kb:read", "docs:read", "chat:ask"]),
}


async def ensure_permission_catalog(session: AsyncSession) -> dict[str, Permission]:
    """补齐缺失的权限记录（幂等）。"""
    existing = {perm.code: perm for perm in (await session.execute(select(Permission))).scalars()}
    for code, name, description in PERMISSION_CATALOG:
        if code not in existing:
            perm = Permission(code=code, name=name, description=description)
            session.add(perm)
            existing[code] = perm
    await session.flush()
    return existing


async def ensure_tenant_roles(session: AsyncSession, tenant_id: int) -> dict[str, Role]:
    """为租户补齐默认角色与角色权限（幂等）。"""
    permissions = await ensure_permission_catalog(session)
    roles = {
        role.code: role
        for role in (
            await session.execute(select(Role).where(Role.tenant_id == tenant_id))
        ).scalars()
    }

    for code, (name, permission_codes) in ROLE_SPECS.items():
        role = roles.get(code)
        if role is None:
            role = Role(
                tenant_id=tenant_id,
                code=code,
                name=name,
                description=f"{name}（系统内置）",
                is_system=True,
            )
            session.add(role)
            await session.flush()
            roles[code] = role

        granted = set(
            (
                await session.execute(
                    select(RolePermission.permission_id).where(RolePermission.role_id == role.id)
                )
            ).scalars()
        )
        wanted = {
            permissions[permission_code].id
            for permission_code in permission_codes
            if permission_code in permissions
        }
        for permission_id in wanted - granted:
            session.add(RolePermission(role_id=role.id, permission_id=permission_id))

    await session.flush()
    return roles


async def assign_roles(session: AsyncSession, user_id: int, role_ids: list[int]) -> None:
    """为用户分配角色（去重，幂等）。"""
    current = set(
        (
            await session.execute(select(UserRole.role_id).where(UserRole.user_id == user_id))
        ).scalars()
    )
    for role_id in dict.fromkeys(role_ids):
        if role_id not in current:
            session.add(UserRole(user_id=user_id, role_id=role_id))
    await session.flush()


async def get_role_codes(session: AsyncSession, user_id: int) -> list[str]:
    """用户角色编码列表。"""
    rows = await session.execute(
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
        .order_by(Role.code)
    )
    return list(rows.scalars())


async def get_permission_codes(session: AsyncSession, user_id: int) -> list[str]:
    """用户权限编码列表（沿 用户→角色→权限 汇总）。"""
    rows = await session.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
    )
    return sorted(set(rows.scalars()))


async def get_role_by_codes(session: AsyncSession, tenant_id: int, codes: list[str]) -> list[Role]:
    """按编码取租户内角色，缺失即报错。"""
    if not codes:
        return []
    roles = list(
        (
            await session.execute(
                select(Role).where(Role.tenant_id == tenant_id, Role.code.in_(codes))
            )
        ).scalars()
    )
    found = {role.code for role in roles}
    missing = [code for code in codes if code not in found]
    if missing:
        raise AppError(
            40001,
            f"角色不存在：{', '.join(missing)}",
            400,
            {"missing_roles": missing},
        )
    return roles
