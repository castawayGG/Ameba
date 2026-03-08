# models/chat_tag.py
# Модели для CRM-тегирования диалогов в разделе /admin/inbox
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Table, Text
from sqlalchemy.sql import func
from core.database import Base


class ChatTag(Base):
    """
    Тег для диалогов/чатов.
    Примеры: "Лид", "Спам", "VIP", "Обработан".
    """
    __tablename__ = 'chat_tags'

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)   # название тега
    color = Column(String(7), default='#6B7280')             # HEX-цвет для отображения
    description = Column(Text, nullable=True)                # необязательное описание
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<ChatTag {self.name}>"


class DialogTag(Base):
    """
    Привязка тега к диалогу.
    Диалог идентифицируется по паре (account_id, peer_id) — аккаунт + собеседник.
    """
    __tablename__ = 'dialog_tags'

    id = Column(Integer, primary_key=True)
    account_id = Column(String(32), ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    peer_id = Column(String(64), nullable=False, index=True)  # Telegram peer ID или username
    tag_id = Column(Integer, ForeignKey('chat_tags.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(String(50), nullable=True)            # пользователь, создавший привязку

    def __repr__(self):
        return f"<DialogTag account={self.account_id} peer={self.peer_id} tag={self.tag_id}>"
