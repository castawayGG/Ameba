"""Add new modules: antidetect, cooldown, spintax, parser, ab_tests

Revision ID: 005_new_modules
Revises: 004_new_features
Create Date: 2026-02-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func

revision = '005_new_modules'
down_revision = '004_new_features'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'antidetect_profiles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('device_model', sa.String(100), nullable=True),
        sa.Column('system_version', sa.String(50), nullable=True),
        sa.Column('app_version', sa.String(50), nullable=True),
        sa.Column('lang_code', sa.String(10), server_default='uk'),
        sa.Column('system_lang_code', sa.String(10), server_default='uk'),
        sa.Column('sdk_version', sa.Integer(), server_default='34'),
        sa.Column('device_hash', sa.String(64), nullable=True),
        sa.Column('account_id', sa.String(64), sa.ForeignKey('accounts.id'), nullable=True),
        sa.Column('is_template', sa.Boolean(), server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
    )

    op.create_table(
        'cooldown_rules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('action_type', sa.String(50), nullable=True),
        sa.Column('min_delay', sa.Integer(), server_default='30'),
        sa.Column('max_delay', sa.Integer(), server_default='120'),
        sa.Column('max_per_hour', sa.Integer(), server_default='20'),
        sa.Column('max_per_day', sa.Integer(), server_default='100'),
        sa.Column('burst_limit', sa.Integer(), server_default='5'),
        sa.Column('burst_cooldown', sa.Integer(), server_default='300'),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
    )

    op.create_table(
        'cooldown_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.String(64), sa.ForeignKey('accounts.id'), nullable=True),
        sa.Column('action_type', sa.String(50), nullable=True),
        sa.Column('performed_at', sa.DateTime(), server_default=func.now()),
        sa.Column('delay_applied', sa.Integer(), nullable=True),
        sa.Column('was_throttled', sa.Boolean(), server_default=sa.false()),
    )

    op.create_table(
        'spintax_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('language', sa.String(10), server_default='uk'),
        sa.Column('variables', sa.JSON(), nullable=True),
        sa.Column('test_count', sa.Integer(), server_default='0'),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
    )

    op.create_table(
        'parse_tasks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(200), nullable=True),
        sa.Column('source_type', sa.String(30), nullable=True),
        sa.Column('source_link', sa.String(500), nullable=True),
        sa.Column('account_id', sa.String(64), sa.ForeignKey('accounts.id'), nullable=True),
        sa.Column('status', sa.String(30), server_default='pending'),
        sa.Column('total_parsed', sa.Integer(), server_default='0'),
        sa.Column('filters', sa.JSON(), nullable=True),
        sa.Column('result_data', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
    )

    op.create_table(
        'ab_tests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('slug', sa.String(100), unique=True, nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('status', sa.String(20), server_default='draft'),
        sa.Column('variants', sa.JSON(), nullable=True),
        sa.Column('total_visits', sa.Integer(), server_default='0'),
        sa.Column('winner_variant', sa.String(50), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
    )

    op.create_table(
        'ab_test_visits',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('test_id', sa.Integer(), sa.ForeignKey('ab_tests.id', ondelete='CASCADE'), nullable=False),
        sa.Column('variant_name', sa.String(50), nullable=False),
        sa.Column('ip', sa.String(45), nullable=True),
        sa.Column('converted', sa.Boolean(), server_default=sa.false()),
        sa.Column('visited_at', sa.DateTime(), server_default=func.now()),
    )


def downgrade() -> None:
    op.drop_table('ab_test_visits')
    op.drop_table('ab_tests')
    op.drop_table('parse_tasks')
    op.drop_table('spintax_templates')
    op.drop_table('cooldown_logs')
    op.drop_table('cooldown_rules')
    op.drop_table('antidetect_profiles')
