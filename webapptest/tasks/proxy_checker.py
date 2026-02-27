from celery import shared_task
from services.proxy.checker import check_proxy_task as async_check_proxy
from core.database import SessionLocal
from models.proxy import Proxy
from core.logger import log
import asyncio

@shared_task(bind=True, max_retries=2)
def check_proxy_task(self, proxy_id: int):
    """
    Фоновая задача для проверки одного прокси.
    """
    try:
        asyncio.run(async_check_proxy(proxy_id))
        return {'success': True, 'proxy_id': proxy_id}
    except Exception as e:
        log.error(f"check_proxy_task for proxy {proxy_id} failed: {e}")
        self.retry(exc=e, countdown=30)

@shared_task
def bulk_check_proxies(proxy_ids: list):
    """
    Массовая проверка прокси (запускает отдельные задачи для каждого).
    """
    for pid in proxy_ids:
        check_proxy_task.delay(pid)
    return {'started': len(proxy_ids)}

@shared_task
def check_all_proxies():
    """
    Периодическая задача для проверки всех прокси (запускается по расписанию).
    """
    db = SessionLocal()
    try:
        proxies = db.query(Proxy).all()
        for proxy in proxies:
            check_proxy_task.delay(proxy.id)
    finally:
        db.close()
    return {'started': len(proxies)}