"""阶段 0：健康检查接口测试。"""

from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    """正常路径：健康检查返回 200 与 {status: ok}。"""
    resp = await client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert resp.headers["content-type"].startswith("application/json")


async def test_health_no_auth_required(client: AsyncClient) -> None:
    """健康检查不需要 Authorization 头。"""
    resp = await client.get("/health", headers={})

    assert resp.status_code == 200


async def test_unknown_path_returns_404(client: AsyncClient) -> None:
    """异常路径：不存在的路由返回统一错误结构。"""
    resp = await client.get("/not-exists")

    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == 40401
    assert body["message"]
    assert isinstance(body["detail"], dict)


async def test_openapi_documents_health(client: AsyncClient) -> None:
    """OpenAPI 中必须包含 /health 描述。"""
    resp = await client.get("/openapi.json")

    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert paths["/health"]["get"]["summary"] == "健康检查"
