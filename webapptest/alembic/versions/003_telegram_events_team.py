"""Add telegram events and team models

Revision ID: 003_telegram_events_team
Revises: 002_add_new_models
Create Date: 2026-02-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func

revision = '003_telegram_events_team'
down_revision = '002_add_new_models'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'telegram_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.String(32), sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('sender_tg_id', sa.String(20), nullable=True),
        sa.Column('sender_username', sa.String(50), nullable=True),
        sa.Column('sender_name', sa.String(200), nullable=True),
        sa.Column('chat_id', sa.String(20), nullable=True),
        sa.Column('chat_title', sa.String(200), nullable=True),
        sa.Column('chat_type', sa.String(20), nullable=True),
        sa.Column('text_preview', sa.Text(), nullable=True),
        sa.Column('media_type', sa.String(30), nullable=True),
        sa.Column('data', sa.JSON(), nullable=True),
        sa.Column('is_processed', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('is_read', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=func.now(), nullable=False),
    )
    op.create_index('ix_telegram_events_account_id', 'telegram_events', ['account_id'])
    op.create_index('ix_telegram_events_event_type', 'telegram_events', ['event_type'])
    op.create_index('ix_telegram_events_created_at', 'telegram_events', ['created_at'])

    op.create_table(
        'incoming_messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.String(32), sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tg_message_id', sa.BigInteger(), nullable=True),
        sa.Column('sender_tg_id', sa.String(20), nullable=False),
        sa.Column('sender_username', sa.String(50), nullable=True),
        sa.Column('sender_name', sa.String(200), nullable=True),
        sa.Column('chat_id', sa.String(20), nullable=False),
        sa.Column('chat_type', sa.String(20), server_default='private', nullable=False),
        sa.Column('chat_title', sa.String(200), nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('media_type', sa.String(30), nullable=True),
        sa.Column('media_file_id', sa.String(200), nullable=True),
        sa.Column('is_outgoing', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('is_read', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('reply_to_msg_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now(), nullable=False),
    )
    op.create_index('ix_incoming_messages_account_id', 'incoming_messages', ['account_id'])
    op.create_index('ix_incoming_messages_sender_tg_id', 'incoming_messages', ['sender_tg_id'])
    op.create_index('ix_incoming_messages_chat_id', 'incoming_messages', ['chat_id'])
    op.create_index('ix_incoming_messages_created_at', 'incoming_messages', ['created_at'])

    op.create_table(
        'alert_rules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('condition', sa.JSON(), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('action_params', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now(), nullable=False),
    )

    op.create_table(
        'forward_rules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.String(32), sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=True),
        sa.Column('filter_type', sa.String(20), server_default='all', nullable=False),
        sa.Column('filter_value', sa.String(500), nullable=True),
        sa.Column('destination_type', sa.String(30), nullable=False),
        sa.Column('destination_value', sa.String(200), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now(), nullable=False),
    )

    op.create_table(
        'comments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('entity_id', sa.String(50), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=func.now(), nullable=False),
    )

    op.create_table(
        'team_tasks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('assigned_to', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status', sa.String(20), server_default='todo', nullable=False),
        sa.Column('priority', sa.String(20), server_default='medium', nullable=False),
        sa.Column('due_date', sa.DateTime(), nullable=True),
        sa.Column('related_entity_type', sa.String(50), nullable=True),
        sa.Column('related_entity_id', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), onupdate=func.now(), nullable=True),
    )

    op.create_table(
        'announcements',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('priority', sa.String(20), server_default='normal', nullable=False),
        sa.Column('is_pinned', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now(), nullable=False),
    )

    op.create_table(
        'shared_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('type', sa.String(30), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('is_shared', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=func.now(), nullable=False),
    )

    op.create_table(
        'user_quotas',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, unique=True),
        sa.Column('max_accounts', sa.Integer(), server_default='100', nullable=False),
        sa.Column('max_campaigns_per_day', sa.Integer(), server_default='10', nullable=False),
        sa.Column('max_messages_per_day', sa.Integer(), server_default='500', nullable=False),
        sa.Column('max_proxy_slots', sa.Integer(), server_default='50', nullable=False),
    )

    op.add_column('users', sa.Column('notification_prefs', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'notification_prefs')

    op.drop_table('user_quotas')
    op.drop_table('shared_templates')
    op.drop_table('announcements')
    op.drop_table('team_tasks')
    op.drop_table('comments')
    op.drop_table('forward_rules')
    op.drop_table('alert_rules')

    op.drop_index('ix_incoming_messages_created_at', table_name='incoming_messages')
    op.drop_index('ix_incoming_messages_chat_id', table_name='incoming_messages')
    op.drop_index('ix_incoming_messages_sender_tg_id', table_name='incoming_messages')
    op.drop_index('ix_incoming_messages_account_id', table_name='incoming_messages')
    op.drop_table('incoming_messages')

    op.drop_index('ix_telegram_events_created_at', table_name='telegram_events')
    op.drop_index('ix_telegram_events_event_type', table_name='telegram_events')
    op.drop_index('ix_telegram_events_account_id', table_name='telegram_events')
    op.drop_table('telegram_events')
