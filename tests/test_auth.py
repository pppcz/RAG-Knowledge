"""阶段 1：多租户、JWT、RBAC 测试（正常路径 + 关键异常路径）。"""

from httpx import AsyncClient

REGISTER_URL = "/api/auth/register"
LOGIN_URL = "/api/auth/login"
ME_URL = "/api/auth/me"
USERS_URL = "/api/auth/users"


def _register_payload(
    tenant_name: str = "Acme",
    tenant_slug: str | None = None,
    username: str = "admin",
    email: str = "admin@example.com",
    password: str = "secret123",
) -> dict[str, str | None]:
    """注册请求体。"""
    payload: dict[str, str | None] = {
        "tenant_name": tenant_name,
        "username": username,
        "email": email,
        "password": password,
    }
    if tenant_slug is not None:
        payload["tenant_slug"] = tenant_slug
    return payload


async def _register(
    client: AsyncClient,
    tenant_name: str = "Acme",
    tenant_slug: str | None = None,
    username: str = "admin",
    email: str = "admin@example.com",
    password: str = "secret123",
) -> dict:
    """注册并返回响应 JSON。"""
    resp = await client.post(
        REGISTER_URL,
        json=_register_payload(tenant_name, tenant_slug, username, email, password),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _headers(token: str) -> dict[str, str]:
    """构造 Bearer 头。"""
    return {"Authorization": f"Bearer {token}"}


async def test_register_creates_tenant_admin(client: AsyncClient) -> None:
    """注册成功：返回令牌，用户为 admin 角色且拥有全部权限。"""
    data = await _register(client, tenant_slug="acme")

    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0
    assert data["access_token"]
    assert data["user"]["username"] == "admin"
    assert data["user"]["tenant_id"] > 0

    me = await client.get(ME_URL, headers=_headers(data["access_token"]))
    assert me.status_code == 200
    body = me.json()
    assert body["user"]["username"] == "admin"
    assert body["roles"] == ["admin"]
    assert "users:read" in body["permissions"]
    assert "users:write" in body["permissions"]
    assert "chat:ask" in body["permissions"]


async def test_register_duplicate_tenant_slug_conflict(client: AsyncClient) -> None:
    """异常路径：重复租户标识返回 409。"""
    await _register(client, tenant_slug="acme")

    resp = await client.post(
        REGISTER_URL,
        json=_register_payload(tenant_name="Other", tenant_slug="acme", username="admin2"),
    )

    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == 40901
    assert "tenant_slug" in body["detail"].get("field", "")


async def test_register_duplicate_username_in_tenant_conflict(client: AsyncClient) -> None:
    """异常路径：同租户内重复用户名返回 409。

    同租户重复注册会创建新租户，因此这里直接构造第二个管理员，
    通过 users:write 接口重复创建同名用户触发冲突。
    """
    data = await _register(client, tenant_slug="acme")
    headers = _headers(data["access_token"])
    user_payload = {
        "username": "member01",
        "email": "member01@example.com",
        "password": "secret123",
        "role_codes": ["member"],
    }

    first = await client.post(USERS_URL, json=user_payload, headers=headers)
    assert first.status_code == 201

    second = await client.post(USERS_URL, json=user_payload, headers=headers)
    assert second.status_code == 409
    assert second.json()["code"] == 40901


async def test_register_validation_error_shape(client: AsyncClient) -> None:
    """异常路径：参数校验失败返回统一错误结构与 40001。"""
    resp = await client.post(
        REGISTER_URL,
        json={"tenant_name": "", "username": "a", "email": "not-an-email", "password": "123"},
    )

    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 40001
    assert body["message"] == "请求参数校验失败"
    assert isinstance(body["detail"]["errors"], list)
    assert body["detail"]["errors"]


async def test_login_success(client: AsyncClient) -> None:
    """正常路径：登录返回可用令牌。"""
    await _register(client, tenant_slug="acme", password="secret123")

    resp = await client.post(LOGIN_URL, json={"username": "admin", "password": "secret123"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["username"] == "admin"

    me = await client.get(ME_URL, headers=_headers(body["access_token"]))
    assert me.status_code == 200


async def test_login_wrong_password(client: AsyncClient) -> None:
    """异常路径：密码错误返回 401 / 40101。"""
    await _register(client, tenant_slug="acme")

    resp = await client.post(LOGIN_URL, json={"username": "admin", "password": "wrong-pass"})

    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == 40101
    assert body["message"] == "用户名或密码错误"


async def test_login_unknown_user(client: AsyncClient) -> None:
    """异常路径：用户不存在返回 401。"""
    resp = await client.post(LOGIN_URL, json={"username": "ghost", "password": "secret123"})

    assert resp.status_code == 401
    assert resp.json()["code"] == 40101


async def test_me_without_token(client: AsyncClient) -> None:
    """异常路径：缺少令牌返回 401。"""
    resp = await client.get(ME_URL)

    assert resp.status_code == 401
    assert resp.json()["code"] == 40101


async def test_me_with_invalid_token(client: AsyncClient) -> None:
    """异常路径：伪造令牌返回 401。"""
    resp = await client.get(ME_URL, headers=_headers("not-a-real-token"))

    assert resp.status_code == 401
    assert resp.json()["code"] == 40101


async def test_me_with_expired_token(client: AsyncClient) -> None:
    """异常路径：过期令牌返回 401 / 40102。"""
    from app.core.security import create_access_token

    data = await _register(client, tenant_slug="acme")
    expired = create_access_token(
        subject=str(data["user"]["id"]),
        tenant_id=data["user"]["tenant_id"],
        roles=["admin"],
        expires_minutes=-5,
    )

    resp = await client.get(ME_URL, headers=_headers(expired))

    assert resp.status_code == 401
    assert resp.json()["code"] == 40102


async def test_tenant_isolation_of_user_list(client: AsyncClient) -> None:
    """多租户隔离：A 租户看不到 B 租户的用户。"""
    tenant_a = await _register(
        client, tenant_name="Tenant A", tenant_slug="tenant-a", username="admin"
    )
    tenant_b = await _register(
        client,
        tenant_name="Tenant B",
        tenant_slug="tenant-b",
        username="admin",
        email="admin-b@example.com",
    )

    created = await client.post(
        USERS_URL,
        json={
            "username": "bob",
            "email": "bob@example.com",
            "password": "secret123",
            "role_codes": ["member"],
        },
        headers=_headers(tenant_b["access_token"]),
    )
    assert created.status_code == 201

    list_a = await client.get(USERS_URL, headers=_headers(tenant_a["access_token"]))
    assert list_a.status_code == 200
    body_a = list_a.json()
    usernames_a = {item["username"] for item in body_a["items"]}
    assert usernames_a == {"admin"}
    assert body_a["total"] == 1

    list_b = await client.get(USERS_URL, headers=_headers(tenant_b["access_token"]))
    usernames_b = {item["username"] for item in list_b.json()["items"]}
    assert usernames_b == {"admin", "bob"}


async def test_same_username_across_tenants_requires_slug(client: AsyncClient) -> None:
    """异常路径：同名用户跨租户时，登录必须提供 tenant_slug。"""
    await _register(client, tenant_name="Tenant A", tenant_slug="tenant-a")
    await _register(
        client,
        tenant_name="Tenant B",
        tenant_slug="tenant-b",
        email="admin-b@example.com",
    )

    ambiguous = await client.post(LOGIN_URL, json={"username": "admin", "password": "secret123"})
    assert ambiguous.status_code == 400
    assert ambiguous.json()["code"] == 40001

    resolved = await client.post(
        LOGIN_URL,
        json={"username": "admin", "password": "secret123", "tenant_slug": "tenant-b"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["user"]["email"] == "admin-b@example.com"


async def test_member_cannot_list_users(client: AsyncClient) -> None:
    """RBAC：member 角色缺少 users:read，返回 403 / 40301。"""
    admin = await _register(client, tenant_slug="acme")
    created = await client.post(
        USERS_URL,
        json={
            "username": "carol",
            "email": "carol@example.com",
            "password": "secret123",
            "role_codes": ["member"],
        },
        headers=_headers(admin["access_token"]),
    )
    assert created.status_code == 201

    login = await client.post(LOGIN_URL, json={"username": "carol", "password": "secret123"})
    assert login.status_code == 200
    member_token = login.json()["access_token"]

    allowed = await client.get(ME_URL, headers=_headers(member_token))
    assert allowed.status_code == 200
    assert allowed.json()["roles"] == ["member"]
    assert "users:read" not in allowed.json()["permissions"]

    forbidden = await client.get(USERS_URL, headers=_headers(member_token))
    assert forbidden.status_code == 403
    body = forbidden.json()
    assert body["code"] == 40301
    assert body["detail"]["required_permission"] == "users:read"


async def test_member_cannot_create_user(client: AsyncClient) -> None:
    """RBAC：member 缺少 users:write，不能创建用户。"""
    admin = await _register(client, tenant_slug="acme")
    await client.post(
        USERS_URL,
        json={
            "username": "dave",
            "email": "dave@example.com",
            "password": "secret123",
            "role_codes": ["member"],
        },
        headers=_headers(admin["access_token"]),
    )
    login = await client.post(LOGIN_URL, json={"username": "dave", "password": "secret123"})
    member_token = login.json()["access_token"]

    resp = await client.post(
        USERS_URL,
        json={
            "username": "eve",
            "email": "eve@example.com",
            "password": "secret123",
        },
        headers=_headers(member_token),
    )

    assert resp.status_code == 403
    assert resp.json()["code"] == 40301


async def test_user_list_pagination_shape(client: AsyncClient) -> None:
    """分页响应结构：items / total / page / page_size。"""
    admin = await _register(client, tenant_slug="acme")
    headers = _headers(admin["access_token"])
    for index in range(3):
        resp = await client.post(
            USERS_URL,
            json={
                "username": f"user{index}",
                "email": f"user{index}@example.com",
                "password": "secret123",
                "role_codes": ["member"],
            },
            headers=headers,
        )
        assert resp.status_code == 201

    resp = await client.get(USERS_URL, params={"page": 1, "page_size": 2}, headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["total"] == 4
    assert len(body["items"]) == 2

    out_of_range = await client.get(USERS_URL, params={"page": 0}, headers=headers)
    assert out_of_range.status_code == 422
    assert out_of_range.json()["code"] == 40001


async def test_create_user_with_unknown_role(client: AsyncClient) -> None:
    """异常路径：分配不存在的角色返回 400。"""
    admin = await _register(client, tenant_slug="acme")

    resp = await client.post(
        USERS_URL,
        json={
            "username": "frank",
            "email": "frank@example.com",
            "password": "secret123",
            "role_codes": ["superuser"],
        },
        headers=_headers(admin["access_token"]),
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == 40001
