"""检索 Schema。"""

from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    """单条检索结果。"""

    chunk_id: int
    document_id: int
    document_title: str
    filename: str
    chunk_index: int
    content: str = Field(..., description="命中切片原文")
    score: float = Field(..., description="余弦相似度，1 表示完全一致")


class SearchResponse(BaseModel):
    """检索响应。"""

    kb_id: int
    query: str
    top_k: int
    total: int
    items: list[SearchHit]
