from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Boolean
from sqlalchemy.sql import func
from core.database import Base

class Task(Base):
    """
    Модель для отслеживания фоновых задач (Celery).
    """
    __tablename__ = 'tasks'

    id = Column(Integer, primary_key=True)
    task_id = Column(String(100), unique=True, index=True)  # ID задачи Celery
    name = Column(String(200), nullable=False)              # Имя задачи
    status = Column(String(50), default='PENDING')          # PENDING, STARTED, SUCCESS, FAILURE, RETRY
    result = Column(JSON, nullable=True)                    # Результат выполнения
    error = Column(Text, nullable=True)                     # Сообщение об ошибке
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    def __repr__(self):
        return f"<Task {self.name} {self.status}>"