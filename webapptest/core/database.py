from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from core.config import Config

# SQLite does not support connection pool parameters
_is_sqlite = Config.SQLALCHEMY_DATABASE_URI.startswith('sqlite')

_pool_kwargs = {} if _is_sqlite else {
    'pool_size': 20,      # размер постоянного пула соединений
    'max_overflow': 10,   # дополнительные соединения сверх pool_size
}

# Создаём движок базы данных
engine = create_engine(
    Config.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,  # проверка соединения перед использованием
    echo=Config.DEBUG,    # логировать SQL-запросы только в режиме отладки
    **_pool_kwargs,
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