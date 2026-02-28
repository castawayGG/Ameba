"""Add new models: notifications, tags, warming, user_sessions and extend existing tables

Revision ID: 002_add_new_models
Revises: 001_health_fields
Create Date: 2026-02-27
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002_add_new_models'
down_revision = '001_health_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add warming_status to accounts
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('warming_status', sa.String(20), nullable=True, server_default='not_warmed'))

    # Add changes JSON column to admin_logs
    with op.batch_alter_table('admin_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('changes', sa.JSON(), nullable=True))

    # Add theme column to users
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('theme', sa.String(20), nullable=True, server_default='dark-blue'))

    # Create notifications table
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('type', sa.String(20), nullable=True, server_default='info'),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=True, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('related_url', sa.String(500), nullable=True),
    )

    # Create tags table
    op.create_table(
        'tags',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(50), nullable=False, unique=True),
        sa.Column('color', sa.String(7), nullable=True, server_default='#6B7280'),
    )

    # Create account_tags association table
    op.create_table(
        'account_tags',
        sa.Column('account_id', sa.String(32), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('tag_id', sa.Integer(), sa.ForeignKey('tags.id'), nullable=False),
    )

    # Create warming_scenarios table
    op.create_table(
        'warming_scenarios',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('actions', sa.JSON(), nullable=True),
        sa.Column('interval_minutes', sa.Integer(), nullable=True, server_default='30'),
        sa.Column('duration_hours', sa.Integer(), nullable=True, server_default='24'),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.true()),
    )

    # Create warming_sessions table
    op.create_table(
        'warming_sessions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.String(32), sa.ForeignKey('accounts.id'), nullable=False),
        sa.Column('scenario_id', sa.Integer(), sa.ForeignKey('warming_scenarios.id'), nullable=False),
        sa.Column('status', sa.String(20), nullable=True, server_default='pending'),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('progress', sa.JSON(), nullable=True),
    )

    # Create user_sessions table
    op.create_table(
        'user_sessions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('session_id', sa.String(128), nullable=False),
        sa.Column('ip', sa.String(45), nullable=False),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('last_active', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_user_sessions_session_id', 'user_sessions', ['session_id'])


def downgrade() -> None:
    op.drop_index('ix_user_sessions_session_id', 'user_sessions')
    op.drop_table('user_sessions')
    op.drop_table('warming_sessions')
    op.drop_table('warming_scenarios')
    op.drop_table('account_tags')
    op.drop_table('tags')
    op.drop_table('notifications')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('theme')

    with op.batch_alter_table('admin_logs', schema=None) as batch_op:
        batch_op.drop_column('changes')

    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.drop_column('warming_status')
