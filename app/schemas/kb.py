"""知识库 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KbCreate(BaseModel):
    """创建知识库。"""

    name: str = Field(..., min_length=1, max_length=128, description="知识库名称")
    description: str | None = Field(None, max_length=512, description="说明")


class KbUpdate(BaseModel):
    """更新知识库（字段均可选）。"""

    name: str | None = Field(None, min_length=1, max_length=128)
    description: str | None = Field(None, max_length=512)


class KbOut(BaseModel):
    """知识库信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    name: str
    description: str | None = None
    document_count: int = Field(0, description="知识库内未删除文档数")
    created_at: datetime
    updated_at: datetime
