# tasks/celery_app.py
# Настройка Celery и расписания периодических задач (Celery Beat)
from celery import Celery
from core.config import Config

celery_app = Celery(
    'ameba',
    broker=Config.CELERY_BROKER_URL,
    backend=Config.CELERY_RESULT_BACKEND,
    include=[
        'tasks.mass_actions',
        'tasks.proxy_checker',
        'tasks.backup',
        'tasks.cleanup',
        'tasks.session_checker',
        'tasks.proxy_fetch',
    ],
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    # Расписание периодических задач
    beat_schedule={
        # Проверка всех сессий аккаунтов каждые 6 часов
        'check-all-sessions': {
            'task': 'tasks.session_checker.check_all_sessions',
            'schedule': 3600 * 6,
        },
        # Обновление бесплатных прокси каждые N часов (из конфига)
        'fetch-free-proxies': {
            'task': 'tasks.proxy_fetch.fetch_and_validate_free_proxies',
            'schedule': 3600 * Config.PROXY_AUTO_REFRESH_HOURS,
        },
        # Проверка всех прокси каждые 2 часа
        'check-all-proxies': {
            'task': 'tasks.proxy_checker.check_all_proxies',
            'schedule': 3600 * 2,
        },
    },
)

if __name__ == '__main__':
    celery_app.start()