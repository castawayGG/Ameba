# tasks/proxy_fetch.py
# Celery-задача для автоматической загрузки и валидации бесплатных прокси
from celery import shared_task
from core.database import SessionLocal
from core.logger import log
from models.proxy import Proxy
from services.proxy.fetcher import fetch_free_proxies


@shared_task
def fetch_and_validate_free_proxies():
    """
    Загружает бесплатные прокси, сохраняет новые в БД и запускает их проверку.
    Запускается по расписанию через Celery Beat (раз в N часов).
    """
    db = SessionLocal()
    try:
        fetched = fetch_free_proxies()
        added = 0
        for p in fetched:
            # Проверяем, нет ли уже такого прокси
            exists = db.query(Proxy).filter(
                Proxy.host == p['host'],
                Proxy.port == p['port'],
            ).first()
            if not exists:
                proxy = Proxy(
                    type=p.get('type', 'http'),
                    host=p['host'],
                    port=p['port'],
                    status='unknown',
                )
                db.add(proxy)
                added += 1
        db.commit()
        log.info(f"fetch_and_validate_free_proxies: added {added} new proxies")

        # Запускаем валидацию только новых прокси (status='unknown')
        unknown = db.query(Proxy).filter(Proxy.status == 'unknown').all()
        from tasks.proxy_checker import check_proxy_task
        for proxy in unknown:
            check_proxy_task.delay(proxy.id)

        return {'fetched': len(fetched), 'added': added, 'validating': len(unknown)}
    except Exception as e:
        db.rollback()
        log.error(f"fetch_and_validate_free_proxies failed: {e}")
        raise
    finally:
        db.close()
