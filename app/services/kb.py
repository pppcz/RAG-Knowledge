"""知识库业务逻辑：CRUD 与默认知识库。"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.schemas.kb import KbCreate, KbOut, KbUpdate

DEFAULT_KB_NAME = "默认知识库"


def to_out(kb: KnowledgeBase, document_count: int = 0) -> KbOut:
    """ORM 转响应对象并填充文档数。"""
    return KbOut.model_validate(kb).model_copy(update={"document_count": document_count})


async def document_count_of_kb(session: AsyncSession, kb_id: int) -> int:
    """统计知识库内未删除文档数。"""
    return (
        await session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.kb_id == kb_id, Document.deleted_at.is_(None))
        )
    ) or 0


async def get_kb(session: AsyncSession, tenant_id: int, kb_id: int) -> KnowledgeBase:
    """按租户取知识库，不存在返回 404。"""
    kb = await session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.tenant_id == tenant_id,
            KnowledgeBase.deleted_at.is_(None),
        )
    )
    if kb is None:
        raise AppError(40401, "知识库不存在", 404)
    return kb


async def create_kb(
    session: AsyncSession,
    tenant_id: int,
    payload: KbCreate,
    created_by: int | None = None,
) -> KbOut:
    """创建知识库，同租户内名称唯一。"""
    duplicate = await session.scalar(
        select(KnowledgeBase.id).where(
            KnowledgeBase.tenant_id == tenant_id,
            KnowledgeBase.name == payload.name,
            KnowledgeBase.deleted_at.is_(None),
        )
    )
    if duplicate is not None:
        raise AppError(40901, f"知识库已存在：{payload.name}", 409, {"field": "name"})

    kb = KnowledgeBase(
        tenant_id=tenant_id,
        name=payload.name,
        description=payload.description,
        created_by=created_by,
    )
    session.add(kb)
    await session.commit()
    return to_out(kb)


async def list_kbs(
    session: AsyncSession,
    tenant_id: int,
    page: int,
    page_size: int,
) -> tuple[list[KbOut], int]:
    """分页列出知识库（附文档数），强制 tenant_id 过滤。"""
    condition = (KnowledgeBase.tenant_id == tenant_id, KnowledgeBase.deleted_at.is_(None))

    total = (
        await session.scalar(select(func.count()).select_from(KnowledgeBase).where(*condition))
    ) or 0

    count_subq = (
        select(Document.kb_id.label("kb_id"), func.count().label("cnt"))
        .where(Document.deleted_at.is_(None))
        .group_by(Document.kb_id)
        .subquery()
    )

    rows = await session.execute(
        select(KnowledgeBase, func.coalesce(count_subq.c.cnt, 0))
        .outerjoin(count_subq, count_subq.c.kb_id == KnowledgeBase.id)
        .where(*condition)
        .order_by(KnowledgeBase.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    items = [to_out(kb, count) for kb, count in rows.all()]
    return items, total


async def update_kb(
    session: AsyncSession,
    tenant_id: int,
    kb_id: int,
    payload: KbUpdate,
) -> KbOut:
    """更新知识库名称 / 说明。"""
    kb = await get_kb(session, tenant_id, kb_id)

    if payload.name is not None and payload.name != kb.name:
        duplicate = await session.scalar(
            select(KnowledgeBase.id).where(
                KnowledgeBase.tenant_id == tenant_id,
                KnowledgeBase.name == payload.name,
                KnowledgeBase.id != kb_id,
                KnowledgeBase.deleted_at.is_(None),
            )
        )
        if duplicate is not None:
            raise AppError(40901, f"知识库已存在：{payload.name}", 409, {"field": "name"})
        kb.name = payload.name

    if payload.description is not None:
        kb.description = payload.description

    await session.commit()
    return to_out(kb, await document_count_of_kb(session, kb.id))


async def delete_kb(session: AsyncSession, tenant_id: int, kb_id: int) -> None:
    """软删除知识库及其下文档。"""
    kb = await get_kb(session, tenant_id, kb_id)

    documents = list(
        (
            await session.execute(
                select(Document).where(
                    Document.kb_id == kb.id,
                    Document.tenant_id == tenant_id,
                    Document.deleted_at.is_(None),
                )
            )
        ).scalars()
    )
    for document in documents:
        document.deleted_at = datetime.now(UTC)

    kb.deleted_at = datetime.now(UTC)
    await session.commit()


async def get_or_create_default_kb(
    session: AsyncSession,
    tenant_id: int,
    created_by: int | None = None,
) -> KnowledgeBase:
    """取默认知识库，不存在时创建（上传未指定 kb_id 时使用）。"""
    kb = await session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.tenant_id == tenant_id,
            KnowledgeBase.name == DEFAULT_KB_NAME,
            KnowledgeBase.deleted_at.is_(None),
        )
    )
    if kb is not None:
        return kb

    kb = KnowledgeBase(
        tenant_id=tenant_id,
        name=DEFAULT_KB_NAME,
        description="未指定知识库时自动创建",
        created_by=created_by,
    )
    session.add(kb)
    await session.flush()
    return kb
