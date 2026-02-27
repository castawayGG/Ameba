# models/account_log.py
# Модель для хранения истории действий с Telegram-аккаунтами
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from core.database import Base


class AccountLog(Base):
    """
    История действий над аккаунтом Telegram.
    Записывается при каждом действии: проверка сессии, отправка сообщения,
    смена пароля, авторизация и т.д.
    """
    __tablename__ = 'account_logs'

    id = Column(Integer, primary_key=True)
    account_id = Column(String(32), ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    action = Column(String(100), nullable=False)       # тип действия: check_session, send_message, re_login...
    result = Column(String(20), default='ok')          # ok / error / warning
    details = Column(Text, nullable=True)              # дополнительная информация
    initiator = Column(String(50), nullable=True)      # пользователь системы или 'system'
    initiator_ip = Column(String(45), nullable=True)   # IP инициатора
    created_at = Column(DateTime, server_default=func.now(), index=True)

    def __repr__(self):
        return f"<AccountLog account={self.account_id} action={self.action}>"
