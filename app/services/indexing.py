"""文档索引：解析 → 切片 → 向量化 → 写入 chunks。"""

import logging

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.models.document import Chunk, Document
from app.services import chunking, embeddings, parser, storage

logger = logging.getLogger(__name__)


async def index_document(session: AsyncSession, document: Document) -> Document:
    """重建单个文档的切片与向量；失败时标记 failed 并写出原因。"""
    document.status = "processing"
    document.error_message = None
    await session.commit()

    try:
        data = await storage.get_storage().get_object(document.storage_key)
        text = parser.extract_text(document.file_ext, data)
        pieces = chunking.split_text(
            text,
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )
        if not pieces:
            raise AppError(42201, "切片结果为空，无法索引", 422)

        embedder = embeddings.get_embedder()
        vectors: list[list[float]] = []
        batch_size = max(1, settings.EMBEDDING_BATCH_SIZE)
        for offset in range(0, len(pieces), batch_size):
            vectors.extend(await embedder.embed_texts(pieces[offset : offset + batch_size]))

        if len(vectors) != len(pieces):
            raise AppError(50001, "向量数量与切片数量不一致", 500)
    except AppError as exc:
        document.status = "failed"
        document.error_message = exc.message[:500]
        await session.commit()
        logger.warning("文档索引失败 id=%s: %s", document.id, exc.message)
        return document
    except Exception as exc:  # 兜底：任何解析/向量化异常都不能让接口 500
        document.status = "failed"
        document.error_message = str(exc)[:500]
        await session.commit()
        logger.exception("文档索引异常 id=%s", document.id)
        return document

    await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
    for index, (content, vector) in enumerate(zip(pieces, vectors, strict=True)):
        session.add(
            Chunk(
                tenant_id=document.tenant_id,
                kb_id=document.kb_id,
                document_id=document.id,
                chunk_index=index,
                content=content,
                char_count=len(content),
                embedding=vector,
            )
        )

    document.chunk_count = len(pieces)
    document.status = "ready"
    document.error_message = None
    await session.commit()
    logger.info("文档索引完成 id=%s chunks=%s", document.id, len(pieces))
    return document
