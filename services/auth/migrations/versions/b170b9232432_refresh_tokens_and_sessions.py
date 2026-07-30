"""refresh tokens and sessions

Revision ID: b170b9232432
Revises: cf257ae4235b
Create Date: 2026-07-29 23:09:25.670086

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b170b9232432'
down_revision: Union[str, None] = 'cf257ae4235b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('sessions',
    sa.Column('id', sa.UUID(as_uuid=False), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('source_ip', sa.String(length=45), server_default=sa.text("''"), nullable=False),
    sa.Column('user_agent', sa.String(length=512), server_default=sa.text("''"), nullable=False),
    sa.Column('revoked', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)
    op.create_table('refresh_tokens',
    sa.Column('jti', sa.UUID(as_uuid=False), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('family_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('session_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('token_hash', sa.String(length=128), nullable=False),
    sa.Column('rotated_from', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('revoked', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('jti'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index(op.f('ix_refresh_tokens_family_id'), 'refresh_tokens', ['family_id'], unique=False)
    op.create_index(op.f('ix_refresh_tokens_session_id'), 'refresh_tokens', ['session_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_refresh_tokens_session_id'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_family_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_table('sessions')
