from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, BigInteger
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from core.database import Base

class IncomingMessage(Base):
    __tablename__ = 'incoming_messages'

    id = Column(Integer, primary_key=True)
    account_id = Column(String(32), ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    tg_message_id = Column(BigInteger, nullable=True)
    sender_tg_id = Column(String(20), nullable=False, index=True)
    sender_username = Column(String(50), nullable=True)
    sender_name = Column(String(200), nullable=True)
    chat_id = Column(String(20), nullable=False, index=True)
    chat_type = Column(String(20), default='private')
    chat_title = Column(String(200), nullable=True)
    text = Column(Text, nullable=True)
    media_type = Column(String(30), nullable=True)
    media_file_id = Column(String(200), nullable=True)
    is_outgoing = Column(Boolean, default=False)
    is_read = Column(Boolean, default=False)
    reply_to_msg_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    assigned_to = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)

    assignee = relationship('User', foreign_keys=[assigned_to])
