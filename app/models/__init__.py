"""ORM 模型统一导出：Alembic 与测试依赖此处的导入注册元数据。"""

from app.models.base import Base, TimestampMixin
from app.models.conversation import Conversation, Message
from app.models.document import Chunk, Document
from app.models.knowledge_base import KnowledgeBase
from app.models.tenant import Tenant
from app.models.user import (
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)

__all__ = [
    "Base",
    "Chunk",
    "Conversation",
    "Document",
    "KnowledgeBase",
    "Message",
    "Permission",
    "Role",
    "RolePermission",
    "Tenant",
    "TimestampMixin",
    "User",
    "UserRole",
]
