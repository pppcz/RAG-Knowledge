"""向量检索：pgvector 余弦距离 + 租户 / 知识库过滤。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Chunk, Document
from app.schemas.search import SearchHit
from app.services import embeddings
from app.services import kb as kb_service


async def search_chunks(
    session: AsyncSession,
    *,
    tenant_id: int,
    kb_id: int,
    query: str,
    top_k: int,
) -> tuple[int, list[SearchHit]]:
    """在指定知识库内按余弦相似度检索切片。

    先校验知识库归属（跨租户直接 404），再用 pgvector 的 `<=>` 算子排序。
    """
    kb = await kb_service.get_kb(session, tenant_id, kb_id)

    embedder = embeddings.get_embedder()
    [query_vector] = await embedder.embed_texts([query])

    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")
    statement = (
        select(Chunk, Document, distance)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.tenant_id == tenant_id,
            Chunk.kb_id == kb.id,
            Chunk.deleted_at.is_(None),
            Chunk.embedding.is_not(None),
            Document.deleted_at.is_(None),
        )
        .order_by(distance)
        .limit(top_k)
    )

    rows = (await session.execute(statement)).all()
    hits = [
        SearchHit(
            chunk_id=chunk.id,
            document_id=document.id,
            document_title=document.title,
            filename=document.filename,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            score=round(1.0 - float(raw_distance), 4),
        )
        for chunk, document, raw_distance in rows
    ]
    return kb.id, hits
