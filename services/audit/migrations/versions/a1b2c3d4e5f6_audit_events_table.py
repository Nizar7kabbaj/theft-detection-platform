"""audit events table

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-08-05 12:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_events',
        sa.Column('sequence_number', sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column('event_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('persisted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('source_service', sa.String(length=64), server_default=sa.text("''"), nullable=False),
        sa.Column('actor', sa.String(length=255), server_default=sa.text("''"), nullable=False),
        sa.Column('severity', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('trace_id', sa.String(length=64), server_default=sa.text("''"), nullable=False),
        sa.Column('event_bytes', sa.LargeBinary(), nullable=False),
        sa.Column('prev_hash', sa.LargeBinary(), nullable=False),
        sa.Column('chain_hash', sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint('sequence_number', name='pk_audit_events'),
        sa.UniqueConstraint('prev_hash', name='uq_audit_events_prev_hash'),
        sa.UniqueConstraint('chain_hash', name='uq_audit_events_chain_hash'),
    )
    op.create_index('ux_audit_events_event_id', 'audit_events', ['event_id'], unique=True)
    op.create_index('ix_audit_events_occurred_at', 'audit_events', ['occurred_at'])
    op.create_index('ix_audit_events_source_service', 'audit_events', ['source_service'])
    op.create_index('ix_audit_events_actor', 'audit_events', ['actor'])
    op.create_index('ix_audit_events_severity', 'audit_events', ['severity'])
    op.execute('GRANT INSERT, SELECT ON TABLE audit_events TO audit_app')


def downgrade() -> None:
    op.execute('REVOKE INSERT, SELECT ON TABLE audit_events FROM audit_app')
    op.drop_index('ix_audit_events_severity', table_name='audit_events')
    op.drop_index('ix_audit_events_actor', table_name='audit_events')
    op.drop_index('ix_audit_events_source_service', table_name='audit_events')
    op.drop_index('ix_audit_events_occurred_at', table_name='audit_events')
    op.drop_index('ux_audit_events_event_id', table_name='audit_events')
    op.drop_table('audit_events')
