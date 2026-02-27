# models/account.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, LargeBinary, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base

class Account(Base):
    __tablename__ = 'accounts'

    id = Column(String(32), primary_key=True)
    phone = Column(String(20), unique=True, nullable=False, index=True)
    username = Column(String(50), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    premium = Column(Boolean, default=False)
    session_data = Column(LargeBinary, nullable=True)
    proxy_id = Column(Integer, ForeignKey('proxies.id'), nullable=True)
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    last_used = Column(DateTime, nullable=True)
    last_checked = Column(DateTime, nullable=True)
    status = Column(String(20), default='active')
    notes = Column(Text, nullable=True)

    proxy = relationship('Proxy', back_populates='accounts')
    # Добавлено back_populates для исключения ошибок доступа из jinja2
    owner = relationship('User', back_populates='accounts', foreign_keys=[owner_id])