"""通用 Schema：错误响应、分页。"""

from typing import Any

from fastapi import Query
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """统一错误结构。"""

    code: int = Field(..., description="业务错误码", examples=[40101])
    message: str = Field(..., description="错误说明", examples=["用户名或密码错误"])
    detail: dict[str, Any] = Field(default_factory=dict, description="附加信息")


class Page[T](BaseModel):
    """统一分页响应。"""

    items: list[T]
    total: int
    page: int
    page_size: int


class PaginationParams:
    """分页查询参数依赖：page >= 1，1 <= page_size <= 100。"""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码，从 1 开始"),
        page_size: int = Query(20, ge=1, le=100, description="每页条数，最大 100"),
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class MessageResponse(BaseModel):
    """简单消息响应。"""

    message: str
