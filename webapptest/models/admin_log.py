from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from core.database import Base

class AdminLog(Base):
    """
    Модель для логирования действий администраторов.
    Каждое действие (вход, удаление, изменение настроек и т.д.) записывается в эту таблицу.
    """
    __tablename__ = 'admin_logs'

    id = Column(Integer, primary_key=True)
    username = Column(String(50), nullable=False, index=True)  # кто совершил действие
    action = Column(String(100), nullable=False, index=True)   # тип действия (login, delete_account, и т.д.)
    details = Column(Text, nullable=True)                      # дополнительные детали (например, ID удалённого аккаунта)
    ip = Column(String(45), nullable=False)                    # IP адрес, с которого пришёл запрос
    user_agent = Column(String(500), nullable=True)            # User-Agent браузера
    timestamp = Column(DateTime, server_default=func.now(), index=True)  # время действия

    def __repr__(self):
        return f"<AdminLog {self.username} {self.action} at {self.timestamp}>"