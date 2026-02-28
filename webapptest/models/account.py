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
    session_file = Column(String(255), nullable=True)       # путь к .session файлу
    proxy_id = Column(Integer, ForeignKey('proxies.id'), nullable=True)
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    last_used = Column(DateTime, nullable=True)
    last_checked = Column(DateTime, nullable=True)
    status = Column(String(20), default='active')
    notes = Column(Text, nullable=True)

    # Расширенные поля для мониторинга здоровья
    flood_wait_until = Column(DateTime, nullable=True)      # время окончания flood wait
    dc_id = Column(Integer, nullable=True)                  # дата-центр Telegram
    tg_id = Column(String(20), nullable=True)               # Telegram user ID
    last_active = Column(DateTime, nullable=True)           # последняя активность аккаунта
    status_detail = Column(Text, nullable=True)             # подробности статуса (причина бана и т.д.)

    warming_status = Column(String(20), default='not_warmed')  # not_warmed, warming, warmed

    proxy = relationship('Proxy', back_populates='accounts')
    # Добавлено back_populates для исключения ошибок доступа из jinja2
    owner = relationship('User', back_populates='accounts', foreign_keys=[owner_id])
    tags = relationship('Tag', secondary='account_tags', backref='accounts')