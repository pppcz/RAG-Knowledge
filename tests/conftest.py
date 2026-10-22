"""pytest 全局夹具：独立测试数据库 + Alembic 迁移 + 用例间清库。

测试数据库与开发库分离：默认 `rag_test`，可通过 TEST_DATABASE_URL 覆盖。
必须在导入 app 之前设置环境变量，因为配置对象在导入时实例化。
"""

import asyncio
import os
import sys
from collections.abc import AsyncIterator

# psycopg 异步驱动不支持 Windows 的 ProactorEventLoop，测试统一使用 Selector
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://rag:rag@localhost:5433/rag_test",
)

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789abcdef0123456789abcdef")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("EMBEDDING_PROVIDER", "hash")
# 测试不依赖 MinIO：使用本地目录存储；上传上限调小便于覆盖超限场景
os.environ["STORAGE_PROVIDER"] = "local"
os.environ["LOCAL_STORAGE_DIR"] = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".pytest-storage"
)
os.environ["MAX_UPLOAD_MB"] = "1"

import psycopg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from app.core.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORAGE_DIR = os.environ["LOCAL_STORAGE_DIR"]

# 按外键依赖倒序截断
TABLES = (
    "role_permissions",
    "user_roles",
    "chunks",
    "documents",
    "knowledge_bases",
    "users",
    "roles",
    "permissions",
    "tenants",
)


def _create_test_database() -> None:
    """若测试库不存在则创建（连接维护库 postgres）。"""
    url = make_url(TEST_DATABASE_URL)
    database = url.database or "rag_test"
    dsn = url.set(drivername="postgresql", database="postgres").render_as_string(
        hide_password=False
    )
    with psycopg.connect(dsn, autocommit=True) as conn:
        exists = conn.execute(
            "select 1 from pg_database where datname = %s", (database,)
        ).fetchone()
        if exists is None:
            conn.execute(f'CREATE DATABASE "{database}"')


@pytest.fixture(scope="session", autouse=True)
def prepare_database() -> None:
    """会话级：建库并执行全部迁移，验证迁移脚本可用。"""
    _create_test_database()
    config = Config(os.path.join(PROJECT_ROOT, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(PROJECT_ROOT, "alembic"))
    command.upgrade(config, "head")


@pytest.fixture(autouse=True)
async def clean_database() -> AsyncIterator[None]:
    """每个用例前清空业务表与本地存储目录，保证用例互不影响。"""
    import shutil

    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
    shutil.rmtree(STORAGE_DIR, ignore_errors=True)
    yield


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """基于 ASGI 传输的测试客户端。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """直连测试库的会话，用于断言落库结果。"""
    async with SessionLocal() as session:
        yield session


@pytest.fixture
async def tenant_admin(client: AsyncClient) -> dict:
    """注册一个租户并返回其管理员令牌与请求头。"""
    resp = await client.post(
        "/api/auth/register",
        json={
            "tenant_name": "Test Tenant",
            "tenant_slug": "test-tenant",
            "username": "admin",
            "email": "admin@example.com",
            "password": "secret123",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return {
        "token": data["access_token"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "user": data["user"],
        "tenant_id": data["user"]["tenant_id"],
    }


@pytest.fixture
async def member_headers(client: AsyncClient, tenant_admin: dict) -> dict:
    """管理员创建 member 用户并返回其请求头。"""
    created = await client.post(
        "/api/auth/users",
        json={
            "username": "member01",
            "email": "member01@example.com",
            "password": "secret123",
            "role_codes": ["member"],
        },
        headers=tenant_admin["headers"],
    )
    assert created.status_code == 201, created.text

    login = await client.post(
        "/api/auth/login", json={"username": "member01", "password": "secret123"}
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
