# models/api_credential.py
# Модель для хранения нескольких пар API ID/Hash (ротация учётных данных Telegram)
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from core.database import Base


class ApiCredential(Base):
    """
    Пара Telegram API ID / API Hash.
    Поддерживает несколько пар для ротации: при каждом запросе
    выбирается случайная активная пара.
    """
    __tablename__ = 'api_credentials'

    id = Column(Integer, primary_key=True)
    label = Column(String(100), nullable=True)         # пользовательское название (опционально)
    api_id = Column(String(20), nullable=False)        # Telegram App API ID
    api_hash = Column(String(64), nullable=False)      # Telegram App API Hash
    enabled = Column(Boolean, default=True)            # активна ли пара
    notes = Column(Text, nullable=True)                # заметки
    created_at = Column(DateTime, server_default=func.now())
    last_used = Column(DateTime, nullable=True)        # время последнего использования
    requests_count = Column(Integer, default=0)        # счётчик запросов

    def __repr__(self):
        return f"<ApiCredential id={self.api_id} label={self.label!r}>"
