"""event subjects index

Revision ID: c9e2f4a17b53
Revises: f2d7b3e845a9
Create Date: 2026-09-05 02:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c9e2f4a17b53'
down_revision: Union[str, None] = 'f2d7b3e845a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'audit_events',
        sa.Column(
            'subjects',
            postgresql.ARRAY(sa.String(length=64)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.create_index(
        'ix_audit_events_subjects',
        'audit_events',
        ['subjects'],
        postgresql_using='gin',
    )
    op.execute("GRANT UPDATE (subjects) ON audit_events TO audit_app")


def downgrade() -> None:
    op.execute("REVOKE UPDATE (subjects) ON audit_events FROM audit_app")
    op.drop_index('ix_audit_events_subjects', table_name='audit_events')
    op.drop_column('audit_events', 'subjects')
