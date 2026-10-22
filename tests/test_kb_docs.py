"""阶段 2：知识库与文档上传测试（正常路径 + 关键异常路径 + 隔离 / RBAC）。"""

from pathlib import Path

from app.core.config import settings
from httpx import AsyncClient

KB_URL = "/api/kb"
DOCS_URL = "/api/docs"
UPLOAD_URL = "/api/docs/upload"


def _storage_root() -> Path:
    """测试使用的本地存储根目录。"""
    return Path(settings.LOCAL_STORAGE_DIR).resolve()


def _stored_files() -> list[Path]:
    """当前已落盘的对象文件。"""
    root = _storage_root()
    if not root.exists():
        return []
    return [path for path in root.rglob("*") if path.is_file()]


async def _create_kb(
    client: AsyncClient,
    headers: dict[str, str],
    name: str = "测试知识库",
) -> dict:
    """创建知识库并返回响应体。"""
    resp = await client.post(KB_URL, json={"name": name}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _upload(
    client: AsyncClient,
    headers: dict[str, str],
    filename: str = "note.txt",
    content: bytes = b"hello rag",
    kb_id: int | None = None,
) -> object:
    """上传文档。"""
    data: dict[str, str] = {}
    if kb_id is not None:
        data["kb_id"] = str(kb_id)
    files = {"file": (filename, content, "text/plain")}
    return await client.post(UPLOAD_URL, files=files, data=data, headers=headers)


async def test_create_and_list_kb(client: AsyncClient, tenant_admin: dict) -> None:
    """正常路径：创建知识库后列表可见，文档数为 0。"""
    created = await _create_kb(client, tenant_admin["headers"])

    assert created["name"] == "测试知识库"
    assert created["tenant_id"] == tenant_admin["tenant_id"]
    assert created["document_count"] == 0

    listing = await client.get(KB_URL, headers=tenant_admin["headers"])
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == created["id"]
    assert body["page"] == 1
    assert body["page_size"] == 20


async def test_create_kb_duplicate_name(client: AsyncClient, tenant_admin: dict) -> None:
    """异常路径：同租户重复名称返回 409。"""
    await _create_kb(client, tenant_admin["headers"])

    resp = await client.post(KB_URL, json={"name": "测试知识库"}, headers=tenant_admin["headers"])

    assert resp.status_code == 409
    assert resp.json()["code"] == 40901


async def test_kb_detail_and_not_found(client: AsyncClient, tenant_admin: dict) -> None:
    """详情返回 200，不存在返回 404。"""
    created = await _create_kb(client, tenant_admin["headers"])

    detail = await client.get(f"{KB_URL}/{created['id']}", headers=tenant_admin["headers"])
    assert detail.status_code == 200
    assert detail.json()["name"] == "测试知识库"

    missing = await client.get(f"{KB_URL}/999999", headers=tenant_admin["headers"])
    assert missing.status_code == 404
    assert missing.json()["code"] == 40401


async def test_update_kb(client: AsyncClient, tenant_admin: dict) -> None:
    """更新名称与说明；改名冲突返回 409。"""
    first = await _create_kb(client, tenant_admin["headers"], name="知识库A")
    await _create_kb(client, tenant_admin["headers"], name="知识库B")

    updated = await client.patch(
        f"{KB_URL}/{first['id']}",
        json={"name": "知识库A2", "description": "新说明"},
        headers=tenant_admin["headers"],
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "知识库A2"
    assert updated.json()["description"] == "新说明"

    conflict = await client.patch(
        f"{KB_URL}/{first['id']}",
        json={"name": "知识库B"},
        headers=tenant_admin["headers"],
    )
    assert conflict.status_code == 409


async def test_delete_kb_soft_deletes(client: AsyncClient, tenant_admin: dict) -> None:
    """删除知识库后详情 404、列表为空。"""
    created = await _create_kb(client, tenant_admin["headers"])

    deleted = await client.delete(f"{KB_URL}/{created['id']}", headers=tenant_admin["headers"])
    assert deleted.status_code == 204

    detail = await client.get(f"{KB_URL}/{created['id']}", headers=tenant_admin["headers"])
    assert detail.status_code == 404

    listing = await client.get(KB_URL, headers=tenant_admin["headers"])
    assert listing.json()["total"] == 0


async def test_member_cannot_create_kb(client: AsyncClient, member_headers: dict) -> None:
    """RBAC：member 缺少 kb:write，创建知识库返回 403。"""
    resp = await client.post(KB_URL, json={"name": "越权库"}, headers=member_headers)

    assert resp.status_code == 403
    assert resp.json()["code"] == 40301
    assert resp.json()["detail"]["required_permission"] == "kb:write"


async def test_upload_txt_to_kb(client: AsyncClient, tenant_admin: dict) -> None:
    """正常路径：上传 TXT 到指定知识库，落盘 + 入库 + 计数。"""
    kb = await _create_kb(client, tenant_admin["headers"])

    resp = await _upload(
        client,
        tenant_admin["headers"],
        filename="note.txt",
        content="报销流程：提交、审批、付款。".encode(),
        kb_id=kb["id"],
    )

    assert resp.status_code == 201
    document = resp.json()
    assert document["kb_id"] == kb["id"]
    assert document["file_ext"] == "txt"
    # 阶段 3 起上传即解析入库，状态直接为 ready
    assert document["status"] == "ready"
    assert document["chunk_count"] >= 1
    assert document["size_bytes"] > 0
    assert len(document["checksum"]) == 64
    assert document["title"] == "note.txt"

    assert _stored_files(), "文件应写入对象存储（测试用本地目录）"

    listing = await client.get(
        DOCS_URL, params={"kb_id": kb["id"]}, headers=tenant_admin["headers"]
    )
    assert listing.json()["total"] == 1

    detail = await client.get(f"{KB_URL}/{kb['id']}", headers=tenant_admin["headers"])
    assert detail.json()["document_count"] == 1


async def test_upload_without_kb_uses_default(client: AsyncClient, tenant_admin: dict) -> None:
    """未指定 kb_id 时写入自动创建的默认知识库（兼容任务书验收命令）。"""
    resp = await _upload(client, tenant_admin["headers"], filename="sample.txt")

    assert resp.status_code == 201
    assert resp.json()["kb_id"] > 0

    kbs = await client.get(KB_URL, headers=tenant_admin["headers"])
    names = [item["name"] for item in kbs.json()["items"]]
    assert names == ["默认知识库"]
    assert kbs.json()["items"][0]["document_count"] == 1


async def test_upload_markdown_and_pdf(client: AsyncClient, tenant_admin: dict) -> None:
    """支持 Markdown 与 PDF 扩展名。"""
    md = await _upload(
        client, tenant_admin["headers"], filename="流程.md", content="# 流程\n\n内容".encode()
    )
    pdf = await _upload(
        client,
        tenant_admin["headers"],
        filename="sample.pdf",
        content=b"%PDF-1.4 fake",
    )

    assert md.status_code == 201
    assert md.json()["file_ext"] == "md"
    assert pdf.status_code == 201
    assert pdf.json()["file_ext"] == "pdf"


async def test_upload_unsupported_extension(client: AsyncClient, tenant_admin: dict) -> None:
    """异常路径：不支持的扩展名返回 415 / 41501。"""
    resp = await _upload(client, tenant_admin["headers"], filename="malware.exe", content=b"MZ")

    assert resp.status_code == 415
    body = resp.json()
    assert body["code"] == 41501
    assert "pdf" in body["detail"]["allowed_extensions"]


async def test_upload_empty_file(client: AsyncClient, tenant_admin: dict) -> None:
    """异常路径：空文件返回 400。"""
    resp = await _upload(client, tenant_admin["headers"], content=b"")

    assert resp.status_code == 400
    assert resp.json()["code"] == 40001


async def test_upload_too_large(client: AsyncClient, tenant_admin: dict) -> None:
    """异常路径：超过 MAX_UPLOAD_MB 返回 413 / 41301。"""
    oversized = b"x" * (1024 * 1024 + 16)

    resp = await _upload(client, tenant_admin["headers"], content=oversized)

    assert resp.status_code == 413
    assert resp.json()["code"] == 41301


async def test_upload_to_foreign_tenant_kb_404(client: AsyncClient, tenant_admin: dict) -> None:
    """异常路径：向其它租户的知识库上传返回 404。"""
    other = await client.post(
        "/api/auth/register",
        json={
            "tenant_name": "Other Tenant",
            "tenant_slug": "other-tenant",
            "username": "admin",
            "email": "other@example.com",
            "password": "secret123",
        },
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    other_kb = await _create_kb(client, other_headers, name="别人的库")

    resp = await _upload(client, tenant_admin["headers"], kb_id=other_kb["id"], content=b"x")

    assert resp.status_code == 404
    assert resp.json()["code"] == 40401


async def test_documents_isolated_between_tenants(client: AsyncClient, tenant_admin: dict) -> None:
    """多租户隔离：B 租户看不到也删不掉 A 租户的文档。"""
    await _upload(client, tenant_admin["headers"], filename="a.txt", content=b"aaa")
    listing_a = await client.get(DOCS_URL, headers=tenant_admin["headers"])
    document_id = listing_a.json()["items"][0]["id"]

    other = await client.post(
        "/api/auth/register",
        json={
            "tenant_name": "Tenant B",
            "tenant_slug": "tenant-b",
            "username": "admin",
            "email": "b@example.com",
            "password": "secret123",
        },
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    assert (await client.get(DOCS_URL, headers=other_headers)).json()["total"] == 0
    assert (await client.get(f"{DOCS_URL}/{document_id}", headers=other_headers)).status_code == 404
    assert (
        await client.delete(f"{DOCS_URL}/{document_id}", headers=other_headers)
    ).status_code == 404
    assert (await client.get(DOCS_URL, headers=tenant_admin["headers"])).json()["total"] == 1


async def test_delete_document_removes_object(client: AsyncClient, tenant_admin: dict) -> None:
    """删除文档：软删除 + 清理存储对象。"""
    await _upload(client, tenant_admin["headers"], filename="to-delete.txt", content=b"data")
    assert _stored_files()

    listing = await client.get(DOCS_URL, headers=tenant_admin["headers"])
    document_id = listing.json()["items"][0]["id"]

    deleted = await client.delete(f"{DOCS_URL}/{document_id}", headers=tenant_admin["headers"])
    assert deleted.status_code == 204

    assert (
        await client.get(f"{DOCS_URL}/{document_id}", headers=tenant_admin["headers"])
    ).status_code == 404
    assert (await client.get(DOCS_URL, headers=tenant_admin["headers"])).json()["total"] == 0
    assert _stored_files() == []


async def test_member_cannot_upload(client: AsyncClient, member_headers: dict) -> None:
    """RBAC：member 缺少 docs:write，上传返回 403。"""
    resp = await _upload(client, member_headers, filename="x.txt", content=b"x")

    assert resp.status_code == 403
    assert resp.json()["detail"]["required_permission"] == "docs:write"
