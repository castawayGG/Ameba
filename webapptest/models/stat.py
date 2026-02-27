from sqlalchemy import Column, Integer, String, DateTime, Date, Float
from sqlalchemy.sql import func
from core.database import Base

class Stat(Base):
    """
    Модель для хранения агрегированной статистики по дням.
    Позволяет быстро строить графики и отчёты без сканирования всех записей.
    """
    __tablename__ = 'stats'

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False, unique=True, index=True)  # дата, за которую собрана статистика

    # Общая статистика
    visits = Column(Integer, default=0)          # количество посещений главной страницы
    phone_submissions = Column(Integer, default=0)  # сколько ввели номер
    code_attempts = Column(Integer, default=0)   # сколько попыток ввода кода
    successful_logins = Column(Integer, default=0)  # успешных входов
    failed_attempts = Column(Integer, default=0)  # неудачных попыток

    # Почасовые данные (хранятся как JSON-строка для гибкости)
    hourly_visits = Column(String, nullable=True)      # JSON: {0: 10, 1: 5, ...}
    hourly_logins = Column(String, nullable=True)      # JSON

    # Конверсия (вычисляемые поля)
    conversion_to_phone = Column(Float, nullable=True)   # visits -> phone_submissions %
    conversion_to_login = Column(Float, nullable=True)   # phone_submissions -> successful_logins %

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    def __repr__(self):
        return f"<Stat {self.date}: visits={self.visits}>"