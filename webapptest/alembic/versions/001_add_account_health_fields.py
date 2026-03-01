"""Add account health monitoring fields

Revision ID: 001_health_fields
Revises:
Create Date: 2026-02-27
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001_health_fields'
down_revision = '000_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to accounts table
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('session_file', sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('flood_wait_until', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('dc_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('tg_id', sa.String(20), nullable=True))
        batch_op.add_column(sa.Column('last_active', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('status_detail', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.drop_column('status_detail')
        batch_op.drop_column('last_active')
        batch_op.drop_column('tg_id')
        batch_op.drop_column('dc_id')
        batch_op.drop_column('flood_wait_until')
        batch_op.drop_column('session_file')
