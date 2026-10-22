"""启用 pgvector，为 chunks 增加向量列与 HNSW 索引。

索引选型：HNSW（vector_cosine_ops）。
- HNSW 无需像 IVFFlat 那样先有训练数据（建索引时表为空也能用），插入即生效；
- 召回率与查询延迟均优于 IVFFlat，适合文档量中等、增量写入的场景；
- 代价是内存与构建时间更高，构建参数保持默认（m=16, ef_construction=64）。

向量维度固定 1536，必须与 EMBEDDING_DIM 一致；如需更换维度需新增迁移。

Revision ID: 0004_pgvector
Revises: 0003_kb_docs
Create Date: 2026-10-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0004_pgvector"
down_revision: str | None = "0003_kb_docs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 1536


def upgrade() -> None:
    """启用 vector 扩展、加向量列、建 HNSW 索引。"""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("chunks", sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True))
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    """删除索引与向量列（保留 vector 扩展）。"""
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.drop_column("chunks", "embedding")
