"""问答接口：SSE 流式问答与会话历史。"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.api.deps import SessionDep, require_permission
from app.models.user import User
from app.schemas.chat import AskRequest, ConversationDetail, ConversationOut
from app.schemas.common import ErrorResponse, Page, PaginationParams
from app.services import chat as chat_service
from app.services import llm as llm_service
from app.services.llm import LLMProvider, LLMUnavailableError, MockLLMProvider

logger = logging.getLogger(__name__)

router = APIRouter()

CHAT_ERRORS = {
    400: {"model": ErrorResponse, "description": "会话与知识库不匹配"},
    401: {"model": ErrorResponse, "description": "未认证"},
    403: {"model": ErrorResponse, "description": "权限不足"},
    404: {"model": ErrorResponse, "description": "知识库或会话不存在"},
    422: {"model": ErrorResponse, "description": "参数校验失败"},
}


async def _stream_tokens(
    provider: LLMProvider,
    messages: list[dict[str, str]],
) -> AsyncIterator[str]:
    """流式产出 token；模型在首个 token 前不可用时自动降级为 mock。"""
    if provider.name == "mock":
        async for token in provider.stream_chat(messages):
            yield token
        return

    try:
        async for token in provider.stream_chat(messages):
            yield token
    except LLMUnavailableError as exc:
        logger.warning("LLM 不可用，降级为 mock 继续回答: %s", exc)
        async for token in MockLLMProvider().stream_chat(messages):
            yield token


@router.post(
    "/ask",
    summary="知识库问答（SSE 流式）",
    description=(
        "基于知识库检索做 RAG 问答，`text/event-stream` 流式返回。\n\n"
        "事件类型：\n"
        '- `message`：`{"delta": "增量文本"}`\n'
        '- `done`：`{"conversation_id", "message_id", "content_length", "citations"}`\n'
        '- `error`：`{"code", "message"}`\n\n'
        "引用包含文档名、片段编号与相似度；LLM 不可用时自动降级为 mock。"
    ),
    responses={
        **CHAT_ERRORS,
        200: {
            "description": "SSE 流",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
    },
)
async def ask(
    payload: AskRequest,
    session: SessionDep,
    current_user: User = Depends(require_permission("chat:ask")),
) -> EventSourceResponse:
    """RAG 问答：先检索并落库用户消息，再流式生成回答。"""
    preparation = await chat_service.prepare_ask(
        session,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        kb_id=payload.kb_id,
        question=payload.question,
        top_k=payload.top_k,
        conversation_id=payload.conversation_id,
    )
    provider = llm_service.get_llm()
    tenant_id = current_user.tenant_id
    logger.info(
        "问答开始 tenant=%s kb=%s provider=%s citations=%s",
        tenant_id,
        payload.kb_id,
        provider.name,
        len(preparation.citations),
    )

    async def event_stream() -> AsyncIterator[dict[str, str]]:
        pieces: list[str] = []
        try:
            async for token in _stream_tokens(provider, preparation.messages):
                pieces.append(token)
                yield {
                    "event": "message",
                    "data": json.dumps({"delta": token}, ensure_ascii=False),
                }
        except asyncio.CancelledError:
            # 客户端断开：保存已生成内容
            if pieces:
                await chat_service.save_assistant_message(
                    tenant_id=tenant_id,
                    conversation_id=preparation.conversation_id,
                    content="".join(pieces),
                    citations=preparation.citations,
                )
            raise
        except Exception as exc:  # 生成过程中的未知异常
            logger.exception("生成回答失败: %s", exc)
            if pieces:
                await chat_service.save_assistant_message(
                    tenant_id=tenant_id,
                    conversation_id=preparation.conversation_id,
                    content="".join(pieces),
                    citations=preparation.citations,
                )
            yield {
                "event": "error",
                "data": json.dumps(
                    {"code": 50001, "message": "生成回答失败，请稍后重试"}, ensure_ascii=False
                ),
            }
            return

        answer = "".join(pieces)
        message_id = await chat_service.save_assistant_message(
            tenant_id=tenant_id,
            conversation_id=preparation.conversation_id,
            content=answer,
            citations=preparation.citations,
        )
        yield {
            "event": "done",
            "data": json.dumps(
                {
                    "conversation_id": preparation.conversation_id,
                    "message_id": message_id,
                    "content_length": len(answer),
                    "citations": [citation.model_dump() for citation in preparation.citations],
                },
                ensure_ascii=False,
            ),
        }

    return EventSourceResponse(event_stream())


@router.get(
    "/history",
    response_model=Page[ConversationOut],
    summary="会话历史列表",
    description=(
        "分页返回当前用户的会话（按 id 倒序，附消息数）。\n\n"
        "需要 chat:ask 权限；严格按 tenant_id + user_id 隔离。"
    ),
    responses=CHAT_ERRORS,
)
async def list_history(
    session: SessionDep,
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(require_permission("chat:ask")),
) -> Page[ConversationOut]:
    """会话列表。"""
    items, total = await chat_service.list_conversations(
        session,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return Page[ConversationOut](
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/history/{conversation_id}",
    response_model=ConversationDetail,
    summary="会话详情",
    description="返回会话及其全部消息（assistant 消息带 citations）；需要 chat:ask 权限。",
    responses=CHAT_ERRORS,
)
async def get_history(
    conversation_id: int,
    session: SessionDep,
    current_user: User = Depends(require_permission("chat:ask")),
) -> ConversationDetail:
    """会话详情。"""
    return await chat_service.get_conversation_detail(
        session,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        conversation_id=conversation_id,
    )
