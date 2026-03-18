"""Add media_files, chat_tags, dialog_tags tables; prepare account_logs partitioning

Revision ID: 013_qol_improvements
Revises: 012_fix_fk_cascade_constraints
Create Date: 2026-03-08

Changes:
- Creates media_files table for the centralized media library
- Creates chat_tags table for CRM inbox tagging
- Creates dialog_tags table (chat/dialog-to-tag mapping)
- On PostgreSQL: converts account_logs to a RANGE-partitioned table by
  created_at (monthly partitions for current + next two months) to prevent
  performance degradation as logs grow.
"""
from alembic import op
import sqlalchemy as sa


revision = '013_qol_improvements'
down_revision = '012_fix_fk_cascade_constraints'
branch_labels = None
depends_on = None


def _dialect():
    return op.get_bind().dialect.name


def upgrade():
    # ------------------------------------------------------------------ #
    # 1. media_files                                                       #
    # ------------------------------------------------------------------ #
    op.create_table(
        'media_files',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('original_name', sa.String(255), nullable=False),
        sa.Column('mime_type', sa.String(100), nullable=False),
        sa.Column('size_bytes', sa.BigInteger, default=0),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('uploaded_by', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('now()'), index=True),
    )

    # ------------------------------------------------------------------ #
    # 2. chat_tags                                                         #
    # ------------------------------------------------------------------ #
    op.create_table(
        'chat_tags',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(50), nullable=False, unique=True),
        sa.Column('color', sa.String(7), default='#6B7280'),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('now()')),
    )

    # ------------------------------------------------------------------ #
    # 3. dialog_tags                                                       #
    # ------------------------------------------------------------------ #
    op.create_table(
        'dialog_tags',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('account_id', sa.String(32),
                  sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('peer_id', sa.String(64), nullable=False, index=True),
        sa.Column('tag_id', sa.Integer,
                  sa.ForeignKey('chat_tags.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('now()')),
        sa.Column('created_by', sa.String(50), nullable=True),
    )
    op.create_index(
        'ix_dialog_tags_account_peer',
        'dialog_tags',
        ['account_id', 'peer_id'],
    )

    # ------------------------------------------------------------------ #
    # 4. account_logs partitioning (PostgreSQL only)                       #
    # ------------------------------------------------------------------ #
    if _dialect() == 'postgresql':
        _partition_account_logs()


def _partition_account_logs():
    """
    Конвертирует таблицу account_logs в секционированную таблицу
    с разбивкой по диапазону дат (месяцы).

    Стратегия «online conversion»:
      1. Переименовать старую таблицу → account_logs_legacy
      2. Создать новую RANGE PARTITIONED таблицу account_logs
      3. Создать начальные партиции (последние 2 месяца + текущий + следующий)
      4. Вставить данные из legacy-таблицы в новую
      5. Удалить legacy-таблицу
    """
    from datetime import date, timedelta

    conn = op.get_bind()

    # Шаг 1: переименовываем существующую таблицу
    conn.execute(sa.text('ALTER TABLE account_logs RENAME TO account_logs_legacy'))

    # Rename old indexes so they don't conflict with new ones
    conn.execute(sa.text('ALTER INDEX IF EXISTS ix_account_logs_account_id RENAME TO ix_account_logs_legacy_account_id'))
    conn.execute(sa.text('ALTER INDEX IF EXISTS ix_account_logs_created_at RENAME TO ix_account_logs_legacy_created_at'))

    # Шаг 2: создаём новую секционированную таблицу
    conn.execute(sa.text("""
        CREATE TABLE account_logs (
            id          SERIAL,
            account_id  VARCHAR(32) NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
            action      VARCHAR(100) NOT NULL,
            result      VARCHAR(20) DEFAULT 'ok',
            details     TEXT,
            initiator   VARCHAR(50),
            initiator_ip VARCHAR(45),
            created_at  TIMESTAMP NOT NULL DEFAULT now()
        ) PARTITION BY RANGE (created_at)
    """))

    conn.execute(sa.text('CREATE INDEX ix_account_logs_account_id ON account_logs (account_id)'))
    conn.execute(sa.text('CREATE INDEX ix_account_logs_created_at ON account_logs (created_at)'))

    # Шаг 3: создаём партиции — от 2 месяцев назад до 1 месяца вперёд
    today = date.today()
    months_to_create = []
    for delta in range(-2, 2):  # -2, -1, 0, +1
        # Safely compute first day of a month relative to today
        total_months = today.year * 12 + today.month - 1 + delta
        year, month = divmod(total_months, 12)
        first_of_month = date(year, month + 1, 1)
        months_to_create.append(first_of_month)

    for m_start in months_to_create:
        # Следующий месяц (exclusive upper bound)
        if m_start.month == 12:
            m_end = m_start.replace(year=m_start.year + 1, month=1)
        else:
            m_end = m_start.replace(month=m_start.month + 1)
        part_name = f"account_logs_{m_start.strftime('%Y_%m')}"
        conn.execute(sa.text(f"""
            CREATE TABLE {part_name}
            PARTITION OF account_logs
            FOR VALUES FROM ('{m_start}') TO ('{m_end}')
        """))

    # Дефолтная партиция для строк, не попавших ни в одну явную партицию
    conn.execute(sa.text("""
        CREATE TABLE account_logs_default
        PARTITION OF account_logs DEFAULT
    """))

    # Шаг 4: переносим данные
    conn.execute(sa.text('INSERT INTO account_logs SELECT * FROM account_logs_legacy'))

    # Шаг 5: удаляем legacy-таблицу
    conn.execute(sa.text('DROP TABLE account_logs_legacy'))


def downgrade():
    # Удаляем новые таблицы
    op.drop_table('dialog_tags')
    op.drop_table('chat_tags')
    op.drop_table('media_files')

    # Партицирование account_logs нельзя откатить без потери данных — пропускаем
    # (в production следует делать отдельный ручной откат)
