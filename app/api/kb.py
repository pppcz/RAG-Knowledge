"""知识库接口。"""

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import SessionDep, require_permission
from app.core.config import settings
from app.models.user import User
from app.schemas.common import ErrorResponse, Page, PaginationParams
from app.schemas.kb import KbCreate, KbOut, KbUpdate
from app.schemas.search import SearchResponse
from app.services import kb as kb_service
from app.services import search as search_service

router = APIRouter()

KB_ERRORS = {
    401: {"model": ErrorResponse, "description": "未认证"},
    403: {"model": ErrorResponse, "description": "权限不足"},
    404: {"model": ErrorResponse, "description": "知识库不存在"},
    409: {"model": ErrorResponse, "description": "知识库名称重复"},
}


@router.post(
    "",
    response_model=KbOut,
    status_code=status.HTTP_201_CREATED,
    summary="创建知识库",
    description="在当前租户下创建知识库，同租户内名称唯一；需要 kb:write 权限。",
    responses=KB_ERRORS,
)
async def create_kb(
    payload: KbCreate,
    session: SessionDep,
    current_user: User = Depends(require_permission("kb:write")),
) -> KbOut:
    """创建知识库。"""
    return await kb_service.create_kb(session, current_user.tenant_id, payload, current_user.id)


@router.get(
    "",
    response_model=Page[KbOut],
    summary="知识库列表",
    description="分页返回当前租户的知识库及其文档数；需要 kb:read 权限。",
    responses=KB_ERRORS,
)
async def list_kbs(
    session: SessionDep,
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(require_permission("kb:read")),
) -> Page[KbOut]:
    """分页列出知识库。"""
    items, total = await kb_service.list_kbs(
        session,
        current_user.tenant_id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return Page[KbOut](
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="知识库检索",
    description=(
        "在指定知识库内做向量检索（pgvector 余弦相似度），返回最相关的切片。\n\n"
        "- 需要 kb:read 权限\n"
        "- `top_k` 默认取 `TOP_K` 配置（5），范围 1-50\n"
        "- 跨租户或知识库不存在返回 404"
    ),
    responses=KB_ERRORS,
)
async def search_knowledge_base(
    session: SessionDep,
    current_user: User = Depends(require_permission("kb:read")),
    kb_id: int = Query(..., ge=1, description="知识库 id"),
    q: str = Query(..., min_length=1, max_length=500, description="查询文本"),
    top_k: int = Query(settings.TOP_K, ge=1, le=50, description="返回条数"),
) -> SearchResponse:
    """向量检索。"""
    resolved_kb_id, hits = await search_service.search_chunks(
        session,
        tenant_id=current_user.tenant_id,
        kb_id=kb_id,
        query=q,
        top_k=top_k,
    )
    return SearchResponse(
        kb_id=resolved_kb_id,
        query=q,
        top_k=top_k,
        total=len(hits),
        items=hits,
    )


@router.get(
    "/{kb_id}",
    response_model=KbOut,
    summary="知识库详情",
    description="按 id 查询当前租户的知识库；需要 kb:read 权限。",
    responses=KB_ERRORS,
)
async def get_kb(
    kb_id: int,
    session: SessionDep,
    current_user: User = Depends(require_permission("kb:read")),
) -> KbOut:
    """知识库详情。"""
    kb = await kb_service.get_kb(session, current_user.tenant_id, kb_id)
    count = await kb_service.document_count_of_kb(session, kb.id)
    return kb_service.to_out(kb, count)


@router.patch(
    "/{kb_id}",
    response_model=KbOut,
    summary="更新知识库",
    description="修改知识库名称或说明；需要 kb:write 权限。",
    responses=KB_ERRORS,
)
async def update_kb(
    kb_id: int,
    payload: KbUpdate,
    session: SessionDep,
    current_user: User = Depends(require_permission("kb:write")),
) -> KbOut:
    """更新知识库。"""
    return await kb_service.update_kb(session, current_user.tenant_id, kb_id, payload)


@router.delete(
    "/{kb_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除知识库",
    description="软删除知识库及其文档；需要 kb:write 权限。",
    responses=KB_ERRORS,
)
async def delete_kb(
    kb_id: int,
    session: SessionDep,
    current_user: User = Depends(require_permission("kb:write")),
) -> None:
    """删除知识库。"""
    await kb_service.delete_kb(session, current_user.tenant_id, kb_id)
