"""Добавление полей для 7 тематических блоков

Revision ID: 007_seven_blocks
Revises: 006_account_management
Create Date: 2026-03-01

Изменения:
- proxies: добавлено поле rotation_url (URL для ротации мобильного прокси)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision = '007_seven_blocks'
down_revision = '006_account_management'
branch_labels = None
depends_on = None


def upgrade():
    # Блок 5: ротация мобильных прокси — URL для API смены IP
    with op.batch_alter_table('proxies') as batch_op:
        batch_op.add_column(sa.Column('rotation_url', sa.String(500), nullable=True))


def downgrade():
    with op.batch_alter_table('proxies') as batch_op:
        batch_op.drop_column('rotation_url')
