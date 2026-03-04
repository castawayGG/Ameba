"""Add granular permissions, per-user Telegram bot settings, and language preference

Revision ID: 011_granular_permissions
Revises: 010_part5_features
Create Date: 2026-03-04
"""
from alembic import op
import sqlalchemy as sa


revision = '011_granular_permissions'
down_revision = '010_part5_features'
branch_labels = None
depends_on = None


def upgrade():
    # Granular permissions JSON dict for each user
    op.add_column('users', sa.Column('permissions', sa.JSON(), nullable=True))
    # Per-user Telegram bot token and chat ID for individual alert routing
    op.add_column('users', sa.Column('tg_bot_token', sa.String(200), nullable=True))
    op.add_column('users', sa.Column('tg_chat_id', sa.String(100), nullable=True))
    # UI language preference ('ru' or 'en')
    op.add_column('users', sa.Column('language', sa.String(10), server_default='ru', nullable=True))


def downgrade():
    op.drop_column('users', 'language')
    op.drop_column('users', 'tg_chat_id')
    op.drop_column('users', 'tg_bot_token')
    op.drop_column('users', 'permissions')
