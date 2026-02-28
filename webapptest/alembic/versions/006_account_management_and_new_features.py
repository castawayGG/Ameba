"""Add account management and new feature tables

Revision ID: 006_account_management
Revises: 005_new_modules
Create Date: 2026-02-28

New tables:
- account_pools
- account_pool_members
- account_fingerprints
- webhooks
- webhook_deliveries
- notes
- api_keys
- panel_settings
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func

revision = '006_account_management'
down_revision = '005_new_modules'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'account_pools',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('selection_strategy', sa.String(20), server_default='round_robin'),
        sa.Column('max_actions_per_account', sa.Integer(), server_default='50'),
        sa.Column('cooldown_minutes', sa.Integer(), server_default='60'),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
    )

    op.create_table(
        'account_pool_members',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pool_id', sa.Integer(), sa.ForeignKey('account_pools.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_id', sa.String(32), sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('added_at', sa.DateTime(), server_default=func.now()),
    )
    op.create_index('ix_account_pool_members_pool', 'account_pool_members', ['pool_id'])
    op.create_index('ix_account_pool_members_account', 'account_pool_members', ['account_id'])

    op.create_table(
        'account_fingerprints',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.String(32), sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('device_model', sa.String(100), nullable=True),
        sa.Column('os_version', sa.String(50), nullable=True),
        sa.Column('app_version', sa.String(50), nullable=True),
        sa.Column('language', sa.String(10), server_default='en'),
        sa.Column('timezone', sa.String(50), server_default='UTC'),
        sa.Column('online_schedule', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
    )
    op.create_index('ix_account_fingerprints_account', 'account_fingerprints', ['account_id'], unique=True)

    op.create_table(
        'webhooks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('url', sa.String(500), nullable=False),
        sa.Column('secret', sa.String(100), nullable=True),
        sa.Column('events', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true()),
        sa.Column('retry_count', sa.Integer(), server_default='3'),
        sa.Column('last_triggered', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
    )

    op.create_table(
        'webhook_deliveries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('webhook_id', sa.Integer(), sa.ForeignKey('webhooks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('response_code', sa.Integer(), nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('success', sa.Boolean(), server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
    )
    op.create_index('ix_webhook_deliveries_webhook', 'webhook_deliveries', ['webhook_id'])

    op.create_table(
        'notes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('entity_type', sa.String(30), nullable=False),
        sa.Column('entity_id', sa.String(64), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=func.now()),
    )
    op.create_index('ix_notes_entity', 'notes', ['entity_type', 'entity_id'])

    op.create_table(
        'api_keys',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('key', sa.String(64), unique=True, nullable=False),
        sa.Column('permissions', sa.JSON(), nullable=True),
        sa.Column('rate_limit', sa.Integer(), server_default='100'),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true()),
        sa.Column('last_used', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
    )
    op.create_index('ix_api_keys_key', 'api_keys', ['key'], unique=True)

    op.create_table(
        'panel_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key', sa.String(100), unique=True, nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
    )
    op.create_index('ix_panel_settings_key', 'panel_settings', ['key'], unique=True)

    # Add indexes for frequently queried columns mentioned in Part 4
    try:
        op.create_index('ix_victims_status', 'victims', ['status'])
    except Exception:
        pass
    try:
        op.create_index('ix_accounts_status', 'accounts', ['status'])
    except Exception:
        pass
    try:
        op.create_index('ix_admin_logs_timestamp', 'admin_logs', ['timestamp'])
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_index('ix_admin_logs_timestamp', 'admin_logs')
    except Exception:
        pass
    try:
        op.drop_index('ix_accounts_status', 'accounts')
    except Exception:
        pass
    try:
        op.drop_index('ix_victims_status', 'victims')
    except Exception:
        pass
    op.drop_index('ix_panel_settings_key', 'panel_settings')
    op.drop_table('panel_settings')
    op.drop_index('ix_api_keys_key', 'api_keys')
    op.drop_table('api_keys')
    op.drop_index('ix_notes_entity', 'notes')
    op.drop_table('notes')
    op.drop_index('ix_webhook_deliveries_webhook', 'webhook_deliveries')
    op.drop_table('webhook_deliveries')
    op.drop_table('webhooks')
    op.drop_index('ix_account_fingerprints_account', 'account_fingerprints')
    op.drop_table('account_fingerprints')
    op.drop_index('ix_account_pool_members_account', 'account_pool_members')
    op.drop_index('ix_account_pool_members_pool', 'account_pool_members')
    op.drop_table('account_pool_members')
    op.drop_table('account_pools')
