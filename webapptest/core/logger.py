import sys
from loguru import logger
from core.config import Config

def setup_logger():
    """
    Настройка логирования с использованием loguru.
    Логи пишутся в консоль, в файл app.log и в JSON-файл для анализа.
    """
    # Удаляем стандартный вывод (чтобы перенастроить)
    logger.remove()

    # Консольный вывод (цветной, с уровнем INFO или DEBUG)
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="DEBUG" if Config.DEBUG else "INFO",
        colorize=True
    )

    # Файл с ротацией (все логи)
    logger.add(
        Config.LOGS_DIR + "/app.log",
        rotation="10 MB",
        retention="1 month",
        format="{time} | {level} | {name}:{function}:{line} - {message}",
        level="DEBUG" if Config.DEBUG else "INFO"
    )

    # JSON-логи для машинной обработки (например, для отправки в ELK)
    logger.add(
        Config.LOGS_DIR + "/json.log",
        rotation="50 MB",
        serialize=True,
        level="INFO"
    )

    # Отдельный файл для ошибок
    logger.add(
        Config.LOGS_DIR + "/errors.log",
        rotation="1 week",
        level="ERROR",
        format="{time} | {level} | {name}:{function}:{line} - {message}"
    )

    return logger

# Глобальный экземпляр логгера
log = setup_logger()