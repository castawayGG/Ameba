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
    # Path to the .session file saved on disk (relative to SESSIONS_DIR)
    session_file = Column(String(200), nullable=True)
    proxy_id = Column(Integer, ForeignKey('proxies.id'), nullable=True)
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    last_used = Column(DateTime, nullable=True)
    last_checked = Column(DateTime, nullable=True)
    status = Column(String(20), default='active')
    notes = Column(Text, nullable=True)
    # Telegram data-centre index (1-5)
    dc_id = Column(Integer, nullable=True)
    # Cloud-password (2FA) enabled flag
    two_fa_enabled = Column(Boolean, default=False)
    # Flood-wait expiry: when not None, the account is under a flood-wait
    flood_wait_until = Column(DateTime, nullable=True)

    proxy = relationship('Proxy', back_populates='accounts')
    # Добавлено back_populates для исключения ошибок доступа из jinja2
    owner = relationship('User', back_populates='accounts', foreign_keys=[owner_id])