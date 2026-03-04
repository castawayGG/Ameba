"""Part 5: quick_reply_templates table, contacts broadcast support

Revision ID: 010_part5_features
Revises: 009_second_wave
Create Date: 2026-03-04
"""
from alembic import op
import sqlalchemy as sa


revision = '010_part5_features'
down_revision = '009_second_wave'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'quick_reply_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.String(100), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('category', sa.String(50), server_default='general'),
        sa.Column('shortcut', sa.String(30), nullable=True, unique=True),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_quick_reply_templates_category', 'quick_reply_templates', ['category'])


def downgrade():
    op.drop_index('ix_quick_reply_templates_category', table_name='quick_reply_templates')
    op.drop_table('quick_reply_templates')
