"""audit event store with hash chain, checkpoints and segments

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
        sa.Column('schema_version', sa.Integer(), server_default=sa.text('1'), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('persisted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('source_service', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('actor', sa.String(length=64), server_default=sa.text("''"), nullable=False),
        sa.Column('severity', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('trace_id', sa.String(length=32), server_default=sa.text("''"), nullable=False),
        sa.Column('payload_kind', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('hash_algorithm', sa.SmallInteger(), server_default=sa.text('1'), nullable=False),
        sa.Column('event_bytes', sa.LargeBinary(), nullable=True),
        sa.Column('leaf_hash', sa.LargeBinary(), nullable=False),
        sa.Column('prev_hash', sa.LargeBinary(), nullable=False),
        sa.Column('chain_hash', sa.LargeBinary(), nullable=False),
        sa.Column('erased_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('erasure_reason', sa.SmallInteger(), server_default=sa.text('0'), nullable=False),
        sa.PrimaryKeyConstraint('sequence_number', name='pk_audit_events'),
        sa.UniqueConstraint('prev_hash', name='uq_audit_events_prev_hash'),
        sa.UniqueConstraint('chain_hash', name='uq_audit_events_chain_hash'),
        sa.CheckConstraint('length(leaf_hash) = 32', name='ck_audit_events_leaf_hash_width'),
        sa.CheckConstraint('length(prev_hash) = 32', name='ck_audit_events_prev_hash_width'),
        sa.CheckConstraint('length(chain_hash) = 32', name='ck_audit_events_chain_hash_width'),
        sa.CheckConstraint('hash_algorithm > 0', name='ck_audit_events_hash_algorithm'),
        sa.CheckConstraint('schema_version > 0', name='ck_audit_events_schema_version'),
        sa.CheckConstraint(
            '(erased_at IS NULL AND event_bytes IS NOT NULL AND erasure_reason = 0)'
            ' OR (erased_at IS NOT NULL AND event_bytes IS NULL AND erasure_reason > 0)',
            name='ck_audit_events_erasure_consistent',
        ),
    )
    op.create_index('ux_audit_events_event_id', 'audit_events', ['event_id'], unique=True)
    op.create_index('ix_audit_events_occurred_at', 'audit_events', ['occurred_at'])
    op.create_index('ix_audit_events_persisted_at', 'audit_events', ['persisted_at'])
    op.create_index('ix_audit_events_source_service', 'audit_events', ['source_service'])
    op.create_index('ix_audit_events_actor', 'audit_events', ['actor'])
    op.create_index('ix_audit_events_severity', 'audit_events', ['severity'])
    op.create_index('ix_audit_events_payload_kind', 'audit_events', ['payload_kind'])
    op.create_index('ix_audit_events_occurred_seq', 'audit_events', ['occurred_at', 'sequence_number'])

    op.create_table(
        'audit_checkpoints',
        sa.Column('checkpoint_id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column('tail_sequence_number', sa.BigInteger(), nullable=False),
        sa.Column('tail_chain_hash', sa.LargeBinary(), nullable=False),
        sa.Column('tree_size', sa.BigInteger(), nullable=False),
        sa.Column('hash_algorithm', sa.SmallInteger(), server_default=sa.text('1'), nullable=False),
        sa.Column('signature_algorithm', sa.SmallInteger(), server_default=sa.text('1'), nullable=False),
        sa.Column('signature', sa.LargeBinary(), nullable=False),
        sa.Column('key_id', sa.String(length=32), nullable=False),
        sa.Column('signed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('prev_checkpoint_hash', sa.LargeBinary(), nullable=False),
        sa.Column('checkpoint_hash', sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint('checkpoint_id', name='pk_audit_checkpoints'),
        sa.UniqueConstraint('tail_sequence_number', name='uq_audit_checkpoints_tail_sequence'),
        sa.UniqueConstraint('checkpoint_hash', name='uq_audit_checkpoints_hash'),
        sa.UniqueConstraint('prev_checkpoint_hash', name='uq_audit_checkpoints_prev_hash'),
        sa.CheckConstraint('length(tail_chain_hash) = 32', name='ck_audit_checkpoints_tail_hash_width'),
        sa.CheckConstraint('length(prev_checkpoint_hash) = 32', name='ck_audit_checkpoints_prev_hash_width'),
        sa.CheckConstraint('length(checkpoint_hash) = 32', name='ck_audit_checkpoints_hash_width'),
        sa.CheckConstraint(
            '(signature_algorithm = 1 AND length(signature) = 64)'
            ' OR (signature_algorithm = 2 AND length(signature) = 2420)',
            name='ck_audit_checkpoints_signature_width',
        ),
        sa.CheckConstraint('tree_size > 0', name='ck_audit_checkpoints_tree_size'),
    )
    op.create_index('ix_audit_checkpoints_signed_at', 'audit_checkpoints', ['signed_at'])

    op.create_table(
        'audit_chain_segments',
        sa.Column('segment_id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column('first_sequence_number', sa.BigInteger(), nullable=False),
        sa.Column('last_sequence_number', sa.BigInteger(), nullable=False),
        sa.Column('first_prev_hash', sa.LargeBinary(), nullable=False),
        sa.Column('terminal_chain_hash', sa.LargeBinary(), nullable=False),
        sa.Column('row_count', sa.BigInteger(), nullable=False),
        sa.Column('hash_algorithm', sa.SmallInteger(), server_default=sa.text('1'), nullable=False),
        sa.Column('covers_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('covers_to', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sealed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('checkpoint_id', sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint('segment_id', name='pk_audit_chain_segments'),
        sa.UniqueConstraint('first_sequence_number', name='uq_audit_chain_segments_first_sequence'),
        sa.UniqueConstraint('last_sequence_number', name='uq_audit_chain_segments_last_sequence'),
        sa.UniqueConstraint('terminal_chain_hash', name='uq_audit_chain_segments_terminal_hash'),
        sa.CheckConstraint('last_sequence_number >= first_sequence_number', name='ck_audit_chain_segments_range'),
        sa.CheckConstraint('length(first_prev_hash) = 32', name='ck_audit_chain_segments_first_hash_width'),
        sa.CheckConstraint('length(terminal_chain_hash) = 32', name='ck_audit_chain_segments_terminal_hash_width'),
        sa.CheckConstraint('row_count > 0', name='ck_audit_chain_segments_row_count'),
        sa.CheckConstraint('covers_to >= covers_from', name='ck_audit_chain_segments_covers'),
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_events_guard() RETURNS trigger AS $$
        BEGIN
            IF current_setting('audit.maintenance', true) = 'on' THEN
                IF TG_OP = 'UPDATE' THEN
                    IF NEW.sequence_number IS DISTINCT FROM OLD.sequence_number
                       OR NEW.event_id IS DISTINCT FROM OLD.event_id
                       OR NEW.leaf_hash IS DISTINCT FROM OLD.leaf_hash
                       OR NEW.prev_hash IS DISTINCT FROM OLD.prev_hash
                       OR NEW.chain_hash IS DISTINCT FROM OLD.chain_hash
                       OR NEW.occurred_at IS DISTINCT FROM OLD.occurred_at
                       OR NEW.persisted_at IS DISTINCT FROM OLD.persisted_at THEN
                        RAISE EXCEPTION 'audit_events: chain columns are immutable';
                    END IF;
                    RETURN NEW;
                END IF;
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'audit_events: % denied on append-only table', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_events_no_update
        BEFORE UPDATE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION audit_events_guard();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_events_no_delete
        BEFORE DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION audit_events_guard();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_checkpoints_guard() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_checkpoints: % denied on append-only table', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_checkpoints_immutable
        BEFORE UPDATE OR DELETE ON audit_checkpoints
        FOR EACH ROW EXECUTE FUNCTION audit_checkpoints_guard();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_chain_segments_guard() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'UPDATE' THEN
                RAISE EXCEPTION 'audit_chain_segments: rows are immutable once sealed';
            END IF;
            IF current_setting('audit.maintenance', true) = 'on' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'audit_chain_segments: % denied outside maintenance', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_chain_segments_guard
        BEFORE UPDATE OR DELETE ON audit_chain_segments
        FOR EACH ROW EXECUTE FUNCTION audit_chain_segments_guard();
        """
    )

    op.execute('GRANT INSERT, SELECT ON TABLE audit_events TO audit_app')
    op.execute('GRANT INSERT, SELECT ON TABLE audit_checkpoints TO audit_app')
    op.execute('GRANT SELECT ON TABLE audit_chain_segments TO audit_app')
    op.execute('REVOKE INSERT ON TABLE audit_chain_segments FROM audit_app')
    op.execute('REVOKE ALL ON TABLE alembic_version FROM audit_app')


def downgrade() -> None:
    op.execute('REVOKE SELECT ON TABLE audit_chain_segments FROM audit_app')
    op.execute('REVOKE INSERT, SELECT ON TABLE audit_checkpoints FROM audit_app')
    op.execute('REVOKE INSERT, SELECT ON TABLE audit_events FROM audit_app')
    op.execute('GRANT INSERT ON TABLE audit_chain_segments TO audit_app')
    op.execute('DROP TRIGGER IF EXISTS trg_audit_chain_segments_guard ON audit_chain_segments')
    op.execute('DROP FUNCTION IF EXISTS audit_chain_segments_guard()')
    op.execute('DROP TRIGGER IF EXISTS trg_audit_checkpoints_immutable ON audit_checkpoints')
    op.execute('DROP FUNCTION IF EXISTS audit_checkpoints_guard()')
    op.execute('DROP TRIGGER IF EXISTS trg_audit_events_no_delete ON audit_events')
    op.execute('DROP TRIGGER IF EXISTS trg_audit_events_no_update ON audit_events')
    op.execute('DROP FUNCTION IF EXISTS audit_events_guard()')
    op.drop_table('audit_chain_segments')
    op.drop_index('ix_audit_checkpoints_signed_at', table_name='audit_checkpoints')
    op.drop_table('audit_checkpoints')
    op.drop_index('ix_audit_events_occurred_seq', table_name='audit_events')
    op.drop_index('ix_audit_events_payload_kind', table_name='audit_events')
    op.drop_index('ix_audit_events_severity', table_name='audit_events')
    op.drop_index('ix_audit_events_actor', table_name='audit_events')
    op.drop_index('ix_audit_events_source_service', table_name='audit_events')
    op.drop_index('ix_audit_events_persisted_at', table_name='audit_events')
    op.drop_index('ix_audit_events_occurred_at', table_name='audit_events')
    op.drop_index('ux_audit_events_event_id', table_name='audit_events')
    op.drop_table('audit_events')
