"""问答 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AskRequest(BaseModel):
    """提问请求。"""

    kb_id: int = Field(..., ge=1, description="知识库 id")
    question: str = Field(..., min_length=1, max_length=1000, description="问题内容")
    conversation_id: int | None = Field(None, ge=1, description="续聊的会话 id，省略则新建会话")
    top_k: int | None = Field(None, ge=1, le=20, description="检索条数，默认取 TOP_K")


class Citation(BaseModel):
    """引用来源。"""

    index: int = Field(..., description="在本次回答中的引用编号，与正文 [n] 对应")
    document_id: int
    document_title: str
    filename: str
    chunk_id: int
    chunk_index: int
    score: float = Field(..., description="余弦相似度")
    snippet: str = Field(..., description="命中片段摘要")


class MessageOut(BaseModel):
    """消息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    citations: list[Citation] | None = None
    created_at: datetime


class ConversationOut(BaseModel):
    """会话摘要。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kb_id: int
    title: str
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


class ConversationDetail(BaseModel):
    """会话详情（含全部消息）。"""

    conversation: ConversationOut
    messages: list[MessageOut]
