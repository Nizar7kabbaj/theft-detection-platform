"""payload erasure grant

Revision ID: f2d7b3e845a9
Revises: a1b2c3d4e5f6
Create Date: 2026-09-05 02:15:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'f2d7b3e845a9'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "GRANT UPDATE (event_bytes, erased_at, erasure_reason) ON audit_events TO audit_app"
    )


def downgrade() -> None:
    op.execute(
        "REVOKE UPDATE (event_bytes, erased_at, erasure_reason) ON audit_events FROM audit_app"
    )
