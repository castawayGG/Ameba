from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from core.config import Config

# Создаём движок базы данных
engine = create_engine(
    Config.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,  # проверка соединения перед использованием
    echo=Config.DEBUG     # логировать SQL-запросы только в режиме отладки
)

# Сессия для работы с БД
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Базовый класс для моделей
Base = declarative_base()

def get_db():
    """
    Генератор для получения сессии БД.
    Используется в зависимостях FastAPI/Flask для автоматического закрытия.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()