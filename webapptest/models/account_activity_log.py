# models/account_activity_log.py
# Журнал активности аккаунта Telegram: каждое действие фиксируется здесь
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base


class AccountActivityLog(Base):
    """
    Журнал активности аккаунта Telegram.
    Хранит историю действий: проверки, реавторизации, массовые операции и т.д.
    """
    __tablename__ = 'account_activity_logs'

    id = Column(Integer, primary_key=True)
    account_id = Column(String(32), ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    action = Column(String(100), nullable=False)        # тип действия (check, relogin, send_message, …)
    result = Column(String(20), nullable=False)         # success / failure / warning
    details = Column(Text, nullable=True)               # подробности (ошибка, контекст)
    initiator_ip = Column(String(45), nullable=True)    # IP инициатора (если вызвано из UI)
    initiator = Column(String(50), nullable=True)       # логин пользователя-инициатора
    timestamp = Column(DateTime, server_default=func.now(), index=True)

    account = relationship('Account', back_populates='activity_logs')

    def __repr__(self):
        return f"<AccountActivityLog account={self.account_id} action={self.action} result={self.result}>"
