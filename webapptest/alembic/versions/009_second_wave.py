"""Second wave: quick_replies table, notification bot settings, log_entries view

Revision ID: 009_second_wave
Revises: 008_part3_features
Create Date: 2026-03-04
"""
from alembic import op
import sqlalchemy as sa


revision = '009_second_wave'
down_revision = '008_part3_features'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'quick_replies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(100), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('category', sa.String(50), server_default='general'),
        sa.Column('shortcut', sa.String(30), nullable=True, unique=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_quick_replies_category', 'quick_replies', ['category'])


def downgrade():
    op.drop_index('ix_quick_replies_category', table_name='quick_replies')
    op.drop_table('quick_replies')
