"""Fix FK cascade constraints for account deletion

Revision ID: 012_fix_fk_cascade_constraints
Revises: 011_granular_permissions
Create Date: 2026-03-08

Adds ON DELETE CASCADE / ON DELETE SET NULL to FK columns that reference
accounts.id so that deleting an account does not raise a FK violation in
PostgreSQL.  In SQLite these constraints are advisory only and the existing
behaviour does not change.
"""
from alembic import op
import sqlalchemy as sa


revision = '012_fix_fk_cascade_constraints'
down_revision = '011_granular_permissions'
branch_labels = None
depends_on = None


def _dialect_name():
    return op.get_bind().dialect.name


def upgrade():
    dialect = _dialect_name()

    if dialect == 'postgresql':
        # warming_sessions.account_id  →  ON DELETE CASCADE
        op.drop_constraint('warming_sessions_account_id_fkey', 'warming_sessions',
                           type_='foreignkey')
        op.create_foreign_key(
            'warming_sessions_account_id_fkey',
            'warming_sessions', 'accounts',
            ['account_id'], ['id'],
            ondelete='CASCADE',
        )

        # cooldown_logs.account_id  →  ON DELETE CASCADE
        op.drop_constraint('cooldown_logs_account_id_fkey', 'cooldown_logs',
                           type_='foreignkey')
        op.create_foreign_key(
            'cooldown_logs_account_id_fkey',
            'cooldown_logs', 'accounts',
            ['account_id'], ['id'],
            ondelete='CASCADE',
        )

        # antidetect_profiles.account_id  →  ON DELETE SET NULL
        op.drop_constraint('antidetect_profiles_account_id_fkey',
                           'antidetect_profiles', type_='foreignkey')
        op.create_foreign_key(
            'antidetect_profiles_account_id_fkey',
            'antidetect_profiles', 'accounts',
            ['account_id'], ['id'],
            ondelete='SET NULL',
        )

        # parse_tasks.account_id  →  ON DELETE SET NULL
        op.drop_constraint('parse_tasks_account_id_fkey', 'parse_tasks',
                           type_='foreignkey')
        op.create_foreign_key(
            'parse_tasks_account_id_fkey',
            'parse_tasks', 'accounts',
            ['account_id'], ['id'],
            ondelete='SET NULL',
        )

        # account_tags.account_id  →  ON DELETE CASCADE
        op.drop_constraint('account_tags_account_id_fkey', 'account_tags',
                           type_='foreignkey')
        op.create_foreign_key(
            'account_tags_account_id_fkey',
            'account_tags', 'accounts',
            ['account_id'], ['id'],
            ondelete='CASCADE',
        )

        # account_tags.tag_id  →  ON DELETE CASCADE
        op.drop_constraint('account_tags_tag_id_fkey', 'account_tags',
                           type_='foreignkey')
        op.create_foreign_key(
            'account_tags_tag_id_fkey',
            'account_tags', 'tags',
            ['tag_id'], ['id'],
            ondelete='CASCADE',
        )
    # SQLite does not support ALTER TABLE for FK constraints; no action needed.


def downgrade():
    dialect = _dialect_name()

    if dialect == 'postgresql':
        # warming_sessions – remove CASCADE
        op.drop_constraint('warming_sessions_account_id_fkey', 'warming_sessions',
                           type_='foreignkey')
        op.create_foreign_key(
            'warming_sessions_account_id_fkey',
            'warming_sessions', 'accounts',
            ['account_id'], ['id'],
        )

        # cooldown_logs – remove CASCADE
        op.drop_constraint('cooldown_logs_account_id_fkey', 'cooldown_logs',
                           type_='foreignkey')
        op.create_foreign_key(
            'cooldown_logs_account_id_fkey',
            'cooldown_logs', 'accounts',
            ['account_id'], ['id'],
        )

        # antidetect_profiles – remove SET NULL
        op.drop_constraint('antidetect_profiles_account_id_fkey',
                           'antidetect_profiles', type_='foreignkey')
        op.create_foreign_key(
            'antidetect_profiles_account_id_fkey',
            'antidetect_profiles', 'accounts',
            ['account_id'], ['id'],
        )

        # parse_tasks – remove SET NULL
        op.drop_constraint('parse_tasks_account_id_fkey', 'parse_tasks',
                           type_='foreignkey')
        op.create_foreign_key(
            'parse_tasks_account_id_fkey',
            'parse_tasks', 'accounts',
            ['account_id'], ['id'],
        )

        # account_tags – remove CASCADE on account_id
        op.drop_constraint('account_tags_account_id_fkey', 'account_tags',
                           type_='foreignkey')
        op.create_foreign_key(
            'account_tags_account_id_fkey',
            'account_tags', 'accounts',
            ['account_id'], ['id'],
        )

        # account_tags – remove CASCADE on tag_id
        op.drop_constraint('account_tags_tag_id_fkey', 'account_tags',
                           type_='foreignkey')
        op.create_foreign_key(
            'account_tags_tag_id_fkey',
            'account_tags', 'tags',
            ['tag_id'], ['id'],
        )
