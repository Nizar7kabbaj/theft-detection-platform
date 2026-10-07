"""telegram bindings

Revision ID: 7c2e9b41d5a3
Revises: e8c4a1f92b70
Create Date: 2026-10-07 09:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = '7c2e9b41d5a3'
down_revision: Union[str, None] = 'e8c4a1f92b70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GRANT = """
DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'auth_app') THEN
    GRANT DELETE ON telegram_bindings TO auth_app;
  END IF;
END
$$;
"""

REVOKE = """
DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'auth_app') THEN
    REVOKE DELETE ON telegram_bindings FROM auth_app;
  END IF;
END
$$;
"""


def upgrade() -> None:
    op.create_table(
        'telegram_bindings',
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            primary_key=True,
        ),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=False, unique=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )
    op.execute(GRANT)


def downgrade() -> None:
    op.execute(REVOKE)
    op.drop_table('telegram_bindings')
