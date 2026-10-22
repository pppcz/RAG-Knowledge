"""基线迁移：仅建立 alembic_version 版本表。

业务表（tenants / users / ...）由后续迁移按依赖顺序创建，
本迁移保持空实现，用于验证 Alembic 工具链可用。

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-18

"""

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """基线：无表结构变更。"""
    pass


def downgrade() -> None:
    """基线：无表结构变更。"""
    pass
