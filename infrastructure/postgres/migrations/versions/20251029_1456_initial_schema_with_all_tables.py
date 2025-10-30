"""initial_schema_with_all_tables

Revision ID: 001_initial
Revises:
Create Date: 2025-10-29 14:56:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables and indexes for the loan prequalification system."""

    # Create applications table
    op.create_table(
        'applications',
        sa.Column('application_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('pan_number_encrypted', sa.LargeBinary(), nullable=False),
        sa.Column('pan_number_hash', sa.String(length=64), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('date_of_birth', sa.TIMESTAMP(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('phone_number', sa.String(length=15), nullable=False),
        sa.Column('requested_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='PENDING'),
        sa.Column('credit_score', sa.Integer(), nullable=True),
        sa.Column('annual_income', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('existing_loans_count', sa.Integer(), nullable=True),
        sa.Column('decision_reason', sa.Text(), nullable=True),
        sa.Column('max_approved_amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )

    # Create indexes for applications table
    op.create_index('idx_applications_pan_hash', 'applications', ['pan_number_hash'], unique=True)
    op.create_index('idx_applications_status', 'applications', ['status'])
    op.create_index('idx_applications_email', 'applications', ['email'])
    op.create_index('idx_applications_created_at', 'applications', ['created_at'])

    # Create audit_log table
    op.create_table(
        'audit_log',
        sa.Column('id', sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column('application_id', UUID(as_uuid=True), sa.ForeignKey('applications.application_id'), nullable=False),
        sa.Column('service_name', sa.String(length=50), nullable=False),
        sa.Column('operation', sa.String(length=50), nullable=False),
        sa.Column('user_id', sa.String(length=100), nullable=True),
        sa.Column('accessed_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )

    # Create indexes for audit_log table
    op.create_index('idx_audit_log_application_id', 'audit_log', ['application_id'])
    op.create_index('idx_audit_log_accessed_at', 'audit_log', ['accessed_at'])
    op.create_index('idx_audit_log_service_name', 'audit_log', ['service_name'])

    # Create processed_messages table
    op.create_table(
        'processed_messages',
        sa.Column('id', sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column('message_id', sa.String(length=255), nullable=False),
        sa.Column('topic_name', sa.String(length=100), nullable=False),
        sa.Column('partition_num', sa.Integer(), nullable=True),
        sa.Column('offset_num', sa.BigInteger(), nullable=True),
        sa.Column('consumer_group', sa.String(length=100), nullable=False),
        sa.Column('processed_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )

    # Create indexes for processed_messages table
    op.create_index('idx_processed_messages_message_id', 'processed_messages', ['message_id'], unique=True)
    op.create_index('idx_processed_messages_topic', 'processed_messages', ['topic_name'])
    op.create_index('idx_processed_messages_processed_at', 'processed_messages', ['processed_at'])

    # Create outbox_events table
    op.create_table(
        'outbox_events',
        sa.Column('id', sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column('aggregate_id', UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('payload', JSONB(), nullable=False),
        sa.Column('topic_name', sa.String(length=100), nullable=False),
        sa.Column('partition_key', sa.String(length=255), nullable=True),
        sa.Column('published', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('published_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )

    # Create indexes for outbox_events table
    op.create_index('idx_outbox_events_published', 'outbox_events', ['published', 'created_at'])
    op.create_index('idx_outbox_events_aggregate_id', 'outbox_events', ['aggregate_id'])
    op.create_index('idx_outbox_events_event_type', 'outbox_events', ['event_type'])


def downgrade() -> None:
    """Drop all tables and indexes."""

    # Drop tables in reverse order (respecting foreign key constraints)
    op.drop_table('outbox_events')
    op.drop_table('processed_messages')
    op.drop_table('audit_log')
    op.drop_table('applications')
