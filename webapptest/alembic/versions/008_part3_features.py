"""Часть 3 — приоритетные функции

Revision ID: 008_part3_features
Revises: 007_seven_blocks
Create Date: 2026-03-04

Изменения:
- incoming_messages: добавлено поле assigned_to (FK на users.id) для передачи чатов
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '008_part3_features'
down_revision = '007_seven_blocks'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('incoming_messages') as batch_op:
        batch_op.add_column(sa.Column('assigned_to', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_incoming_messages_assigned_to_users',
            'users', ['assigned_to'], ['id'],
            ondelete='SET NULL'
        )
        batch_op.create_index('ix_incoming_messages_assigned_to', ['assigned_to'])


def downgrade():
    with op.batch_alter_table('incoming_messages') as batch_op:
        batch_op.drop_index('ix_incoming_messages_assigned_to')
        batch_op.drop_constraint('fk_incoming_messages_assigned_to_users', type_='foreignkey')
        batch_op.drop_column('assigned_to')
