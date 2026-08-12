from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = 'a3f1c8d24e07'
down_revision: Union[str, None] = 'd5999f9fda15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens",
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("replaced_by", UUID(as_uuid=False), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("refresh_tokens", "replaced_by")
    op.drop_column("refresh_tokens", "rotated_at")
