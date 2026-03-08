"""
Задача мониторинга длины очереди Celery.
Периодически проверяет количество задач в очереди Redis и отправляет алерт
через Telegram-бот, если длина превышает порог CELERY_QUEUE_ALERT_THRESHOLD.
"""
import redis
from tasks.celery_app import celery_app
from core.config import Config
from core.logger import log


def _send_telegram_alert(text: str) -> None:
    """Отправляет сообщение через Telegram Bot API."""
    token = Config.NOTIFICATION_BOT_TOKEN
    chat_id = Config.NOTIFICATION_CHAT_ID
    if not token or not chat_id:
        return
    try:
        import requests as _requests
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        _requests.post(url, json={'chat_id': chat_id, 'text': text}, timeout=10)
    except Exception as e:
        log.warning(f"queue_monitor: failed to send Telegram alert: {e}")


@celery_app.task(name='tasks.queue_monitor.check_queue_length', bind=True, max_retries=3)
def check_queue_length(self):
    """
    Проверяет длину очереди 'celery' в Redis.
    Если очередь превышает CELERY_QUEUE_ALERT_THRESHOLD — отправляет алерт в Telegram.
    """
    try:
        r = redis.from_url(Config.REDIS_URL, socket_connect_timeout=5)
        queue_len = r.llen('celery')
        threshold = Config.CELERY_QUEUE_ALERT_THRESHOLD
        log.info(f"Celery queue length: {queue_len} (threshold: {threshold})")
        if queue_len > threshold:
            msg = (
                f"⚠️ *Ameba Alert*: Очередь Celery перегружена!\n"
                f"Текущая длина: *{queue_len}* задач\n"
                f"Порог: {threshold}\n"
                f"Проверьте состояние воркеров."
            )
            _send_telegram_alert(msg)
        return {'queue_length': queue_len, 'threshold': threshold, 'alert_sent': queue_len > threshold}
    except Exception as exc:
        log.error(f"check_queue_length error: {exc}")
        raise self.retry(exc=exc, countdown=60)
