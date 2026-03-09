from celery import Celery
from core.config import Config

# Инициализация Sentry для Celery (если задан SENTRY_DSN)
if Config.SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    sentry_sdk.init(
        dsn=Config.SENTRY_DSN,
        integrations=[CeleryIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

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
        'tasks.event_listener_task',
        'tasks.automation_runner',
        'tasks.scheduled_reports',
        'tasks.queue_monitor',
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
        # Проверка всех прокси каждые 2 часа
        'check-all-proxies': {
            'task': 'tasks.proxy_checker.check_all_proxies',
            'schedule': 7200,
        },
        # Мониторинг длины очереди Celery каждые 5 минут
        'monitor-celery-queue': {
            'task': 'tasks.queue_monitor.check_queue_length',
            'schedule': 300,
        },
    },
)

if __name__ == '__main__':
    celery_app.start()