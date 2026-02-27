# models/api_credential.py
# Модель для хранения нескольких пар API ID/Hash (ротация API ключей Telegram)
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from core.database import Base


class ApiCredential(Base):
    """
    Пара Telegram API ID / API Hash.
    Поддерживает ротацию: при каждом запросе выбирается случайная активная пара.
    """
    __tablename__ = 'api_credentials'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=True)           # пользовательское название (опционально)
    api_id = Column(String(20), nullable=False)
    api_hash = Column(String(64), nullable=False)
    enabled = Column(Boolean, default=True)             # можно отключить без удаления
    description = Column(Text, nullable=True)
    last_used = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<ApiCredential id={self.api_id} name={self.name!r}>"
