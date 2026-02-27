# tasks/proxy_autoloader.py
# Задача Celery: автоматическая загрузка бесплатных прокси и их проверка
import asyncio
import re
from celery import shared_task
from core.database import SessionLocal
from models.proxy import Proxy
from core.logger import log


FREE_PROXY_SOURCES = [
    # Текстовый список из sslproxies.org/free-proxy-list.net
    'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt',
    'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt',
]


@shared_task(name='tasks.proxy_autoloader.auto_load_proxies')
def auto_load_proxies():
    """
    Периодическая задача: загружает бесплатные прокси из публичных источников,
    добавляет новые в базу данных и запускает их проверку.
    """
    import requests as req

    db = SessionLocal()
    added = 0
    try:
        for url in FREE_PROXY_SOURCES:
            # Определяем тип прокси из URL
            proxy_type = 'socks5' if 'socks5' in url else 'http'
            try:
                resp = req.get(url, timeout=15)
                if resp.status_code != 200:
                    log.warning(f"proxy_autoloader: failed to fetch {url}: HTTP {resp.status_code}")
                    continue
                lines = [l.strip() for l in resp.text.splitlines() if l.strip()]
                # Загружаем существующие хосты одним запросом (избегаем N+1)
                existing_pairs = set(
                    (p.host, p.port) for p in db.query(Proxy.host, Proxy.port).all()
                )
                for line in lines:
                    # Формат: host:port
                    m = re.match(r'^([\d.]+):(\d+)$', line)
                    if not m:
                        continue
                    host, port = m.group(1), int(m.group(2))
                    if (host, port) in existing_pairs:
                        continue
                    proxy = Proxy(
                        type=proxy_type,
                        host=host,
                        port=port,
                        status='unknown',
                        enabled=True,
                    )
                    db.add(proxy)
                    existing_pairs.add((host, port))
                    added += 1
                db.commit()
                log.info(f"proxy_autoloader: added {added} proxies from {url}")
            except Exception as e:
                log.error(f"proxy_autoloader: error fetching {url}: {e}")

        # Запускаем массовую проверку всех новых (unknown) прокси
        from tasks.proxy_checker import bulk_check_proxies
        unknown_ids = [p.id for p in db.query(Proxy).filter_by(status='unknown').all()]
        if unknown_ids:
            bulk_check_proxies.delay(unknown_ids)
            log.info(f"proxy_autoloader: queued {len(unknown_ids)} proxies for validation")

        return {'added': added, 'queued_for_check': len(unknown_ids) if unknown_ids else 0}
    finally:
        db.close()
