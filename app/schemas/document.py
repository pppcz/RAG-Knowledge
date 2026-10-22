"""文档 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentOut(BaseModel):
    """文档信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    kb_id: int
    title: str
    filename: str
    file_ext: str
    content_type: str | None = None
    size_bytes: int
    checksum: str | None = None
    status: str = Field(..., description="pending / processing / ready / failed")
    error_message: str | None = None
    chunk_count: int = 0
    created_at: datetime
    updated_at: datetime
