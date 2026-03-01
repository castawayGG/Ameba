"""Initial schema: create all base tables

Revision ID: 000_initial_schema
Revises:
Create Date: 2026-02-27

Creates the foundational tables that subsequent migrations expect to exist:
- users
- proxies
- accounts (without fields added by 001/002)
- campaigns
- admin_logs (without 'changes' field added by 002)
- account_logs
- stats
- tasks
- api_credentials
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func

# revision identifiers, used by Alembic.
revision = '000_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users — no FK dependencies
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('username', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('password_hash', sa.String(128), nullable=False),
        sa.Column('otp_secret', sa.String(32), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('role', sa.String(20), server_default='admin', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.Column('login_attempts', sa.Integer(), server_default='0'),
        sa.Column('locked_until', sa.DateTime(), nullable=True),
    )

    # proxies — no FK dependencies
    op.create_table(
        'proxies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('type', sa.String(10), server_default='socks5'),
        sa.Column('host', sa.String(100), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(100), nullable=True),
        sa.Column('password', sa.String(100), nullable=True),
        sa.Column('name', sa.String(200), nullable=True),
        sa.Column('country', sa.String(50), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), server_default='unknown'),
        sa.Column('enabled', sa.Boolean(), server_default=sa.true()),
        sa.Column('speed', sa.Integer(), nullable=True),
        sa.Column('avg_speed', sa.Float(), nullable=True),
        sa.Column('last_check', sa.DateTime(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('requests_count', sa.Integer(), server_default='0'),
        sa.Column('success_count', sa.Integer(), server_default='0'),
        sa.Column('fail_count', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
    )

    # accounts — depends on proxies, users
    op.create_table(
        'accounts',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('phone', sa.String(20), unique=True, nullable=False, index=True),
        sa.Column('username', sa.String(50), nullable=True),
        sa.Column('first_name', sa.String(100), nullable=True),
        sa.Column('last_name', sa.String(100), nullable=True),
        sa.Column('premium', sa.Boolean(), server_default=sa.false()),
        sa.Column('session_data', sa.LargeBinary(), nullable=True),
        sa.Column('proxy_id', sa.Integer(), sa.ForeignKey('proxies.id'), nullable=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
        sa.Column('last_used', sa.DateTime(), nullable=True),
        sa.Column('last_checked', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(20), server_default='active'),
        sa.Column('notes', sa.Text(), nullable=True),
    )

    # campaigns — depends on users
    op.create_table(
        'campaigns',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('target_type', sa.String(20), nullable=False),
        sa.Column('target_list', sa.JSON(), nullable=False),
        sa.Column('message_template', sa.Text(), nullable=False),
        sa.Column('variations', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(20), server_default='draft'),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('total_targets', sa.Integer(), server_default='0'),
        sa.Column('processed', sa.Integer(), server_default='0'),
        sa.Column('successful', sa.Integer(), server_default='0'),
        sa.Column('failed', sa.Integer(), server_default='0'),
    )

    # admin_logs — no FK dependencies (username is a plain string)
    op.create_table(
        'admin_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('username', sa.String(50), nullable=False, index=True),
        sa.Column('action', sa.String(100), nullable=False, index=True),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('ip', sa.String(45), nullable=False),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('timestamp', sa.DateTime(), server_default=func.now(), index=True),
    )

    # account_logs — depends on accounts
    op.create_table(
        'account_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.String(32), sa.ForeignKey('accounts.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('result', sa.String(20), server_default='ok'),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('initiator', sa.String(50), nullable=True),
        sa.Column('initiator_ip', sa.String(45), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now(), index=True),
    )

    # stats — no FK dependencies
    op.create_table(
        'stats',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('date', sa.Date(), unique=True, nullable=False, index=True),
        sa.Column('visits', sa.Integer(), server_default='0'),
        sa.Column('phone_submissions', sa.Integer(), server_default='0'),
        sa.Column('code_attempts', sa.Integer(), server_default='0'),
        sa.Column('successful_logins', sa.Integer(), server_default='0'),
        sa.Column('failed_attempts', sa.Integer(), server_default='0'),
        sa.Column('hourly_visits', sa.String(), nullable=True),
        sa.Column('hourly_logins', sa.String(), nullable=True),
        sa.Column('conversion_to_phone', sa.Float(), nullable=True),
        sa.Column('conversion_to_login', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # tasks — no FK dependencies
    op.create_table(
        'tasks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('task_id', sa.String(100), unique=True, index=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('status', sa.String(50), server_default='PENDING'),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # api_credentials — no FK dependencies
    op.create_table(
        'api_credentials',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('label', sa.String(100), nullable=True),
        sa.Column('api_id', sa.String(20), nullable=False),
        sa.Column('api_hash', sa.String(64), nullable=False),
        sa.Column('enabled', sa.Boolean(), server_default=sa.true()),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
        sa.Column('last_used', sa.DateTime(), nullable=True),
        sa.Column('requests_count', sa.Integer(), server_default='0'),
    )


def downgrade() -> None:
    op.drop_table('api_credentials')
    op.drop_table('tasks')
    op.drop_table('stats')
    op.drop_table('account_logs')
    op.drop_table('admin_logs')
    op.drop_table('campaigns')
    op.drop_table('accounts')
    op.drop_table('proxies')
    op.drop_table('users')
