"""会话与消息：问答准备、落库与历史查询。"""

import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.errors import AppError
from app.models.base import utcnow
from app.models.conversation import Conversation, Message
from app.schemas.chat import (
    Citation,
    ConversationDetail,
    ConversationOut,
    MessageOut,
)
from app.services import kb as kb_service
from app.services import rag
from app.services import search as search_service

logger = logging.getLogger(__name__)


@dataclass
class AskPreparation:
    """流式回答前的准备结果。"""

    conversation_id: int
    messages: list[dict[str, str]]
    citations: list[Citation]


async def _resolve_conversation(
    session: AsyncSession,
    *,
    tenant_id: int,
    user_id: int,
    kb_id: int,
    conversation_id: int | None,
    question: str,
) -> Conversation:
    """续聊时校验归属（同租户 + 同用户 + 同知识库），否则新建会话。"""
    if conversation_id is None:
        conversation = Conversation(
            tenant_id=tenant_id,
            kb_id=kb_id,
            user_id=user_id,
            title=question.strip()[:80] or "新会话",
        )
        session.add(conversation)
        await session.flush()
        return conversation

    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        )
    )
    if conversation is None:
        raise AppError(40401, "会话不存在", 404)
    if conversation.kb_id != kb_id:
        raise AppError(40001, "会话与知识库不匹配", 400, {"expected_kb_id": conversation.kb_id})
    return conversation


async def prepare_ask(
    session: AsyncSession,
    *,
    tenant_id: int,
    user_id: int,
    kb_id: int,
    question: str,
    top_k: int | None = None,
    conversation_id: int | None = None,
) -> AskPreparation:
    """检索 + 组装 Prompt + 记录用户消息。"""
    kb = await kb_service.get_kb(session, tenant_id, kb_id)
    _, hits = await search_service.search_chunks(
        session,
        tenant_id=tenant_id,
        kb_id=kb.id,
        query=question,
        top_k=top_k or settings.TOP_K,
    )

    conversation = await _resolve_conversation(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        kb_id=kb.id,
        conversation_id=conversation_id,
        question=question,
    )

    citations = [Citation(**item) for item in rag.build_citations(hits)]
    messages = rag.build_messages(question, hits)

    session.add(
        Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            role="user",
            content=question.strip(),
        )
    )
    await session.commit()

    return AskPreparation(
        conversation_id=conversation.id,
        messages=messages,
        citations=citations,
    )


async def save_assistant_message(
    *,
    tenant_id: int,
    conversation_id: int,
    content: str,
    citations: list[Citation],
) -> int:
    """独立会话写入 assistant 消息（流式结束后调用）。"""
    async with SessionLocal() as session:
        message = Message(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            citations=[citation.model_dump() for citation in citations] or None,
        )
        session.add(message)

        conversation = await session.get(Conversation, conversation_id)
        if conversation is not None:
            conversation.updated_at = utcnow()

        await session.commit()
        return message.id


async def list_conversations(
    session: AsyncSession,
    *,
    tenant_id: int,
    user_id: int,
    page: int,
    page_size: int,
) -> tuple[list[ConversationOut], int]:
    """分页列出当前用户的会话（附带消息数）。"""
    conditions = (
        Conversation.tenant_id == tenant_id,
        Conversation.user_id == user_id,
        Conversation.deleted_at.is_(None),
    )
    total = (
        await session.scalar(select(func.count()).select_from(Conversation).where(*conditions))
    ) or 0

    count_subquery = (
        select(Message.conversation_id.label("conversation_id"), func.count().label("cnt"))
        .where(Message.deleted_at.is_(None))
        .group_by(Message.conversation_id)
        .subquery()
    )

    rows = await session.execute(
        select(Conversation, func.coalesce(count_subquery.c.cnt, 0))
        .outerjoin(count_subquery, count_subquery.c.conversation_id == Conversation.id)
        .where(*conditions)
        .order_by(Conversation.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    items = [
        ConversationOut.model_validate(conversation).model_copy(
            update={"message_count": message_count}
        )
        for conversation, message_count in rows.all()
    ]
    return items, total


async def get_conversation_detail(
    session: AsyncSession,
    *,
    tenant_id: int,
    user_id: int,
    conversation_id: int,
) -> ConversationDetail:
    """会话详情：按 id 顺序返回全部消息。"""
    conversation = await session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        )
    )
    if conversation is None:
        raise AppError(40401, "会话不存在", 404)

    messages = list(
        (
            await session.execute(
                select(Message)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.deleted_at.is_(None),
                )
                .order_by(Message.id)
            )
        ).scalars()
    )

    return ConversationDetail(
        conversation=ConversationOut.model_validate(conversation).model_copy(
            update={"message_count": len(messages)}
        ),
        messages=[MessageOut.model_validate(message) for message in messages],
    )
