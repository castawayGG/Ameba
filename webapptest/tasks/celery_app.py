from celery import Celery
from core.config import Config

celery_app = Celery(
    'tasks',
    broker=Config.CELERY_BROKER_URL,
    backend=Config.CELERY_RESULT_BACKEND,
    include=[
        'tasks.mass_actions',
        'tasks.proxy_checker',
        'tasks.backup',
        'tasks.cleanup',
        'tasks.session_checker',
        'tasks.proxy_autoloader',
    ]
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,
    task_soft_time_limit=25 * 60,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    result_expires=3600,
    beat_schedule={
        # Проверка всех сессий каждые 6 часов
        'check-all-sessions': {
            'task': 'tasks.session_checker.check_all_sessions',
            'schedule': Config.PROXY_REFRESH_HOURS * 3600,
        },
        # Автозагрузка бесплатных прокси каждые N часов
        'auto-load-proxies': {
            'task': 'tasks.proxy_autoloader.auto_load_proxies',
            'schedule': Config.PROXY_REFRESH_HOURS * 3600,
        },
        # Проверка всех прокси каждые 2 часа
        'check-all-proxies': {
            'task': 'tasks.proxy_checker.check_all_proxies',
            'schedule': 7200,
        },
    },
)

if __name__ == '__main__':
    celery_app.start()