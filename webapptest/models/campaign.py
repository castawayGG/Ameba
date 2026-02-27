from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base

class Campaign(Base):
    """
    Модель для фишинговых кампаний.
    Позволяет создавать отдельные кампании с разными целевыми страницами,
    сообщениями и отслеживать статистику по каждой.
    """
    __tablename__ = 'campaigns'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)                # Название кампании
    description = Column(Text, nullable=True)                 # Описание
    target_type = Column(String(20), nullable=False)          # 'contacts', 'groups', 'channels'
    target_list = Column(JSON, nullable=False)                # Список целей (контакты/ссылки на группы)
    message_template = Column(Text, nullable=False)           # Шаблон сообщения
    variations = Column(JSON, nullable=True)                  # Варианты текста для рандомизации
    status = Column(String(20), default='draft')              # 'draft', 'running', 'paused', 'completed'
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    total_targets = Column(Integer, default=0)                # Общее количество целей
    processed = Column(Integer, default=0)                    # Сколько обработано
    successful = Column(Integer, default=0)                   # Сколько успешно
    failed = Column(Integer, default=0)                        # Сколько с ошибками

    # Связь с создателем
    creator = relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f"<Campaign {self.name}>"