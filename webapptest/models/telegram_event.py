from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.sql import func
from core.database import Base

class TelegramEvent(Base):
    __tablename__ = 'telegram_events'

    id = Column(Integer, primary_key=True)
    account_id = Column(String(32), ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    sender_tg_id = Column(String(20), nullable=True)
    sender_username = Column(String(50), nullable=True)
    sender_name = Column(String(200), nullable=True)
    chat_id = Column(String(20), nullable=True)
    chat_title = Column(String(200), nullable=True)
    chat_type = Column(String(20), nullable=True)
    text_preview = Column(Text, nullable=True)
    media_type = Column(String(30), nullable=True)
    data = Column(JSON, nullable=True)
    is_processed = Column(Boolean, default=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now(), index=True)
