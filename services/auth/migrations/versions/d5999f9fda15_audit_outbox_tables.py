"""audit outbox tables

Revision ID: d5999f9fda15
Revises: b170b9232432
Create Date: 2026-08-11 13:03:45.497499

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5999f9fda15'
down_revision: Union[str, None] = 'b170b9232432'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('audit_outbox',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('event_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('event_bytes', sa.LargeBinary(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id')
    )
    op.create_index(op.f('ix_audit_outbox_next_attempt_at'), 'audit_outbox', ['next_attempt_at'], unique=False)
    op.create_table('audit_outbox_dead',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('event_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('event_bytes', sa.LargeBinary(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('last_status', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('failed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id')
    )


def downgrade() -> None:
    op.drop_table('audit_outbox_dead')
    op.drop_index(op.f('ix_audit_outbox_next_attempt_at'), table_name='audit_outbox')
    op.drop_table('audit_outbox')
