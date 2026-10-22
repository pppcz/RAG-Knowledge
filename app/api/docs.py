"""文档接口。"""

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.api.deps import SessionDep, require_permission
from app.models.user import User
from app.schemas.common import ErrorResponse, Page, PaginationParams
from app.schemas.document import DocumentOut
from app.services import document as document_service
from app.services import indexing

router = APIRouter()

DOC_ERRORS = {
    400: {"model": ErrorResponse, "description": "文件为空或参数错误"},
    401: {"model": ErrorResponse, "description": "未认证"},
    403: {"model": ErrorResponse, "description": "权限不足"},
    404: {"model": ErrorResponse, "description": "文档或知识库不存在"},
    413: {"model": ErrorResponse, "description": "文件超过大小限制"},
    415: {"model": ErrorResponse, "description": "不支持的文件类型"},
    502: {"model": ErrorResponse, "description": "对象存储不可用"},
}


@router.post(
    "/upload",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    summary="上传文档",
    description=(
        "上传 PDF / Word(.docx) / Markdown / TXT 文档。\n\n"
        "- `kb_id` 省略时写入当前租户的默认知识库（自动创建）\n"
        "- 校验扩展名与大小（`MAX_UPLOAD_MB`，默认 20 MB）\n"
        "- 文件写入对象存储，元数据入库，状态为 `pending`（解析完成后转 `ready`）\n"
        "- 需要 docs:write 权限"
    ),
    responses=DOC_ERRORS,
)
async def upload_document(
    session: SessionDep,
    file: UploadFile = File(..., description="待上传文件"),
    kb_id: int | None = Form(None, description="知识库 id，省略则用默认知识库"),
    title: str | None = Form(None, description="文档标题，默认取文件名"),
    current_user: User = Depends(require_permission("docs:write")),
) -> DocumentOut:
    """上传文档。"""
    return await document_service.upload_document(
        session,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        kb_id=kb_id,
        upload=file,
        title=title,
    )


@router.get(
    "",
    response_model=Page[DocumentOut],
    summary="文档列表",
    description="分页返回当前租户的文档，可按 `kb_id` 过滤；需要 docs:read 权限。",
    responses=DOC_ERRORS,
)
async def list_documents(
    session: SessionDep,
    kb_id: int | None = None,
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(require_permission("docs:read")),
) -> Page[DocumentOut]:
    """分页列出文档。"""
    items, total = await document_service.list_documents(
        session,
        tenant_id=current_user.tenant_id,
        kb_id=kb_id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return Page[DocumentOut](
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentOut,
    summary="文档详情",
    description="按 id 查询当前租户的文档；需要 docs:read 权限。",
    responses=DOC_ERRORS,
)
async def get_document(
    document_id: int,
    session: SessionDep,
    current_user: User = Depends(require_permission("docs:read")),
) -> DocumentOut:
    """文档详情。"""
    document = await document_service.get_document(session, current_user.tenant_id, document_id)
    return DocumentOut.model_validate(document)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除文档",
    description="软删除文档并清理对象存储文件；需要 docs:write 权限。",
    responses=DOC_ERRORS,
)
async def delete_document(
    document_id: int,
    session: SessionDep,
    current_user: User = Depends(require_permission("docs:write")),
) -> None:
    """删除文档。"""
    await document_service.delete_document(session, current_user.tenant_id, document_id)


@router.post(
    "/{document_id}/reindex",
    response_model=DocumentOut,
    summary="重建文档索引",
    description=(
        "重新解析文档、切片并写入 pgvector，覆盖原有切片。\n\n"
        "- 需要 docs:write 权限\n"
        "- 解析失败时返回 200，`status=failed` 且 `error_message` 说明原因\n"
        "- 成功时 `status=ready`，`chunk_count` 为切片数"
    ),
    responses=DOC_ERRORS,
)
async def reindex_document(
    document_id: int,
    session: SessionDep,
    current_user: User = Depends(require_permission("docs:write")),
) -> DocumentOut:
    """重建单个文档的切片与向量。"""
    document = await document_service.get_document(session, current_user.tenant_id, document_id)
    indexed = await indexing.index_document(session, document)
    return DocumentOut.model_validate(indexed)
