"""HTTP 路由聚合：统一前缀 /api。"""

from fastapi import APIRouter

from app.api import auth, chat, docs, kb

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(kb.router, prefix="/kb", tags=["knowledge-base"])
api_router.include_router(docs.router, prefix="/docs", tags=["documents"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])

__all__ = ["api_router"]
