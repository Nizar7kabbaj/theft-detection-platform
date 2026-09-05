"""account erasure grants

Revision ID: e8c4a1f92b70
Revises: a3f1c8d24e07
Create Date: 2026-09-05 02:15:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e8c4a1f92b70'
down_revision: Union[str, None] = 'a3f1c8d24e07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GRANT = """
DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'auth_app') THEN
    GRANT DELETE ON users, sessions, refresh_tokens TO auth_app;
  END IF;
END
$$;
"""

REVOKE = """
DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'auth_app') THEN
    REVOKE DELETE ON users, sessions, refresh_tokens FROM auth_app;
  END IF;
END
$$;
"""


def upgrade() -> None:
    op.execute(GRANT)


def downgrade() -> None:
    op.execute(REVOKE)
