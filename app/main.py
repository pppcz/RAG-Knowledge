"""FastAPI 应用入口。"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import api_router
from app.core import asyncio_compat
from app.core.config import settings
from app.core.errors import register_exception_handlers

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """启动 / 关闭日志，不依赖任何外部服务是否可用。"""
    loop_warning = asyncio_compat.unsupported_loop_message(asyncio.get_running_loop())
    if loop_warning:
        logger.warning(loop_warning)
    logger.info(
        "starting %s env=%s llm=%s embedding=%s",
        settings.APP_NAME,
        settings.APP_ENV,
        settings.LLM_PROVIDER,
        settings.EMBEDDING_PROVIDER,
    )
    yield
    logger.info("stopped %s", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description=(
        "企业知识库 RAG 问答平台后端。\n\n"
        "- 多租户 + RBAC + JWT\n"
        "- 知识库与文档管理、pgvector 检索\n"
        "- SSE 流式问答与引用溯源\n\n"
        '错误响应统一结构：`{"code": int, "message": str, "detail": {}}`'
    ),
    lifespan=lifespan,
)

register_exception_handlers(app)
app.include_router(api_router)


@app.get(
    "/health",
    tags=["system"],
    summary="健康检查",
    description="返回服务存活状态，不依赖数据库、Redis、MinIO 与外部模型服务。",
)
async def health() -> dict[str, str]:
    """健康检查：无鉴权、无外部依赖。"""
    return {"status": "ok"}
