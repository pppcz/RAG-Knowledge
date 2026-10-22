"""文档上传、列表、删除业务逻辑。"""

import hashlib
import logging
from datetime import UTC, datetime

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.models.document import Document
from app.schemas.document import DocumentOut
from app.services import indexing, storage
from app.services import kb as kb_service

logger = logging.getLogger(__name__)

# 支持的文件类型（需与 parser 保持一致）
ALLOWED_EXTENSIONS: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "md": "text/markdown",
    "txt": "text/plain",
}

READ_CHUNK_BYTES = 1024 * 1024


def extension_of(filename: str) -> str:
    """取小写扩展名（不含点）。"""
    _, _, ext = filename.rpartition(".")
    return ext.lower() if ext and "." in filename else ""


async def _read_limited(upload: UploadFile) -> bytes:
    """按上限读取上传内容，超出立即拒绝。"""
    limit = settings.upload_limit_bytes
    buffer = bytearray()

    while True:
        chunk = await upload.read(READ_CHUNK_BYTES)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise AppError(
                41301,
                f"文件超过大小限制（{settings.MAX_UPLOAD_MB} MB）",
                413,
                {"limit_bytes": limit},
            )

    if not buffer:
        raise AppError(40001, "上传文件为空", 400)

    return bytes(buffer)


async def upload_document(
    session: AsyncSession,
    *,
    tenant_id: int,
    user_id: int,
    kb_id: int | None,
    upload: UploadFile,
    title: str | None = None,
) -> DocumentOut:
    """校验类型与大小，写入对象存储并登记文档记录。"""
    filename = (upload.filename or "").strip()
    if not filename:
        raise AppError(40001, "缺少文件名", 400)

    ext = extension_of(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise AppError(
            41501,
            f"不支持的文件类型：{ext or '未知'}",
            415,
            {"allowed_extensions": sorted(ALLOWED_EXTENSIONS)},
        )

    data = await _read_limited(upload)

    if kb_id is None:
        kb = await kb_service.get_or_create_default_kb(session, tenant_id, created_by=user_id)
    else:
        kb = await kb_service.get_kb(session, tenant_id, kb_id)

    checksum = hashlib.sha256(data).hexdigest()
    document = Document(
        tenant_id=tenant_id,
        kb_id=kb.id,
        title=(title or filename)[:255],
        filename=filename[:255],
        file_ext=ext,
        content_type=upload.content_type or ALLOWED_EXTENSIONS[ext],
        size_bytes=len(data),
        checksum=checksum,
        storage_key="",
        status="pending",
        uploader_id=user_id,
    )
    session.add(document)
    await session.flush()

    storage_key = storage.build_storage_key(tenant_id, kb.id, document.id, filename)
    document.storage_key = storage_key

    backend = storage.get_storage()
    try:
        await backend.put_object(
            storage_key, data, document.content_type or "application/octet-stream"
        )
    except AppError:
        await session.rollback()
        raise
    except Exception as exc:  # 兜底：存储异常不留下脏记录
        await session.rollback()
        logger.exception("文档上传失败 filename=%s", filename)
        raise AppError(50201, "文件保存失败", 502) from exc

    await session.commit()
    logger.info(
        "文档上传成功 id=%s tenant=%s kb=%s size=%s",
        document.id,
        tenant_id,
        kb.id,
        len(data),
    )

    # 上传后立即解析、切片、向量化；失败只标记 failed，不影响上传结果
    await indexing.index_document(session, document)
    return DocumentOut.model_validate(document)


async def list_documents(
    session: AsyncSession,
    *,
    tenant_id: int,
    kb_id: int | None,
    page: int,
    page_size: int,
) -> tuple[list[DocumentOut], int]:
    """分页列出文档，强制 tenant_id 过滤。"""
    conditions = [Document.tenant_id == tenant_id, Document.deleted_at.is_(None)]
    if kb_id is not None:
        conditions.append(Document.kb_id == kb_id)

    total = (
        await session.scalar(select(func.count()).select_from(Document).where(*conditions))
    ) or 0

    documents = list(
        (
            await session.execute(
                select(Document)
                .where(*conditions)
                .order_by(Document.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars()
    )
    return [DocumentOut.model_validate(document) for document in documents], total


async def get_document(session: AsyncSession, tenant_id: int, document_id: int) -> Document:
    """按租户取文档，不存在返回 404。"""
    document = await session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == tenant_id,
            Document.deleted_at.is_(None),
        )
    )
    if document is None:
        raise AppError(40401, "文档不存在", 404)
    return document


async def delete_document(session: AsyncSession, tenant_id: int, document_id: int) -> None:
    """软删除文档，并尽力清理对象存储。"""
    document = await get_document(session, tenant_id, document_id)
    storage_key = document.storage_key

    document.deleted_at = datetime.now(UTC)
    await session.commit()

    if storage_key:
        await storage.get_storage().delete_object(storage_key)
