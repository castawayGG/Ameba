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
    'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt',
]


@shared_task(name='tasks.proxy_autoloader.auto_load_proxies')
def auto_load_proxies(proxy_type_filter=None, country_filter=None):
    """
    Периодическая задача: загружает бесплатные прокси из публичных источников,
    добавляет новые в базу данных и запускает их проверку.

    Args:
        proxy_type_filter: фильтр по типу прокси (socks5, socks4, http) или None для всех
        country_filter: фильтр по стране (код ISO, напр. 'US', 'RU') или None для всех
    """
    import requests as req

    db = SessionLocal()
    added = 0
    try:
        sources = FREE_PROXY_SOURCES
        if proxy_type_filter:
            sources = [u for u in sources if proxy_type_filter.lower() in u.lower()]
            if not sources:
                sources = FREE_PROXY_SOURCES

        for url in sources:
            # Определяем тип прокси из URL
            if 'socks5' in url:
                proxy_type = 'socks5'
            elif 'socks4' in url:
                proxy_type = 'socks4'
            else:
                proxy_type = 'http'

            if proxy_type_filter and proxy_type != proxy_type_filter.lower():
                continue

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

        # Определяем страну прокси через GeoIP (если фильтр задан)
        if country_filter:
            try:
                _tag_proxy_countries(db, country_filter)
            except Exception as e:
                log.error(f"proxy_autoloader: country tagging error: {e}")

        # Запускаем массовую проверку всех новых (unknown) прокси
        from tasks.proxy_checker import bulk_check_proxies
        query = db.query(Proxy).filter_by(status='unknown')
        if country_filter:
            query = query.filter(Proxy.country == country_filter.upper())
        unknown_ids = [p.id for p in query.all()]
        if unknown_ids:
            bulk_check_proxies.delay(unknown_ids)
            log.info(f"proxy_autoloader: queued {len(unknown_ids)} proxies for validation")

        return {'added': added, 'queued_for_check': len(unknown_ids) if unknown_ids else 0}
    finally:
        db.close()


def _tag_proxy_countries(db, country_filter=None):
    """Пытается определить страну прокси по IP через бесплатный GeoIP API."""
    import requests as req

    untagged = db.query(Proxy).filter(Proxy.country.is_(None)).limit(100).all()
    for proxy in untagged:
        try:
            resp = req.get(f'http://ip-api.com/json/{proxy.host}?fields=countryCode', timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                proxy.country = data.get('countryCode', '')
        except Exception:
            pass
    db.commit()


def _batch_geoip_lookup(hosts: list) -> dict:
    """
    Определяет страну для списка IP-адресов через batch API ip-api.com.
    Возвращает словарь {host: country_code}.
    ip-api.com позволяет до 100 IP за запрос (бесплатный тариф: 45 запросов/мин).
    """
    import requests as req

    result = {}
    batch_size = 100
    for i in range(0, len(hosts), batch_size):
        batch = hosts[i:i + batch_size]
        try:
            payload = [{'query': h, 'fields': 'query,countryCode,status'} for h in batch]
            resp = req.post('http://ip-api.com/batch', json=payload, timeout=15)
            if resp.status_code == 200:
                for entry in resp.json():
                    if entry.get('status') == 'success':
                        result[entry['query']] = entry.get('countryCode', '')
        except Exception as e:
            log.warning(f"proxy_autoloader: batch GeoIP error: {e}")
    return result


def _fetch_candidate_proxies(proxy_type_filter=None) -> list:
    """
    Загружает кандидатов-прокси из публичных источников.
    Возвращает список словарей {'host', 'port', 'type'}.
    """
    import requests as req

    candidates = []
    for url in FREE_PROXY_SOURCES:
        if 'socks5' in url:
            proxy_type = 'socks5'
        elif 'socks4' in url:
            proxy_type = 'socks4'
        else:
            proxy_type = 'http'

        if proxy_type_filter and proxy_type != proxy_type_filter.lower():
            continue

        try:
            resp = req.get(url, timeout=15)
            if resp.status_code != 200:
                log.warning(f"proxy_autoloader: failed to fetch {url}: HTTP {resp.status_code}")
                continue
            for line in resp.text.splitlines():
                line = line.strip()
                m = re.match(r'^([\d.]+):(\d+)$', line)
                if m:
                    candidates.append({'host': m.group(1), 'port': int(m.group(2)), 'type': proxy_type})
        except Exception as e:
            log.error(f"proxy_autoloader: error fetching {url}: {e}")

    return candidates


def auto_upload_proxies(region: str, count: int) -> dict:
    """
    Синхронная функция авто-загрузки прокси для указанного региона.
    Загружает из публичных источников, определяет страну через GeoIP и добавляет
    в базу данных ровно ``count`` прокси (или меньше, если не хватает доступных).

    Args:
        region: ISO-код страны (напр. 'RU', 'US')
        count:  желаемое количество прокси (1..PROXY_AUTO_UPLOAD_MAX)

    Returns:
        dict с ключами: created (int), requested (int), errors (list[str]),
                        proxies (list[dict]) — созданные прокси
    """
    from core.database import SessionLocal

    db = SessionLocal()
    created = 0
    errors = []
    added_proxies = []
    try:
        region_upper = region.upper()

        # Загрузка кандидатов из всех источников
        candidates = _fetch_candidate_proxies()
        if not candidates:
            errors.append('Не удалось загрузить прокси из публичных источников')
            return {'created': 0, 'requested': count, 'errors': errors, 'proxies': []}

        # Убираем дубли внутри кандидатов
        seen = set()
        unique_candidates = []
        for c in candidates:
            key = (c['host'], c['port'])
            if key not in seen:
                seen.add(key)
                unique_candidates.append(c)

        # Загружаем уже существующие пары host:port из БД
        existing_pairs = set(
            (p.host, p.port) for p in db.query(Proxy.host, Proxy.port).all()
        )

        # Отфильтровываем уже существующие
        new_candidates = [c for c in unique_candidates if (c['host'], c['port']) not in existing_pairs]

        if not new_candidates:
            errors.append('Все загруженные прокси уже существуют в базе данных')
            return {'created': 0, 'requested': count, 'errors': errors, 'proxies': []}

        # Batch GeoIP lookup для новых кандидатов
        hosts_to_lookup = [c['host'] for c in new_candidates]
        country_map = _batch_geoip_lookup(hosts_to_lookup)

        # Фильтрация по региону и добавление в БД
        for c in new_candidates:
            if created >= count:
                break
            country = country_map.get(c['host'], '')
            if country.upper() != region_upper:
                continue
            savepoint = db.begin_nested()
            try:
                proxy = Proxy(
                    type=c['type'],
                    host=c['host'],
                    port=c['port'],
                    country=country,
                    status='unknown',
                    enabled=True,
                )
                db.add(proxy)
                db.flush()  # получаем id без commit
                savepoint.commit()
                added_proxies.append({
                    'id': proxy.id,
                    'host': proxy.host,
                    'port': proxy.port,
                    'type': proxy.type,
                    'country': proxy.country,
                })
                created += 1
            except Exception as e:
                savepoint.rollback()
                errors.append(f'{c["host"]}:{c["port"]}: {e}')

        if created < count:
            errors.append(
                f'Доступно только {created} прокси для региона {region_upper} '
                f'из публичных источников'
            )

        db.commit()

        log.info(
            f"auto_upload_proxies: region={region_upper}, requested={count}, "
            f"created={created}, errors={len(errors)}"
        )
        return {'created': created, 'requested': count, 'errors': errors, 'proxies': added_proxies}

    except Exception as e:
        db.rollback()
        log.error(f"auto_upload_proxies: unexpected error: {e}")
        return {'created': created, 'requested': count, 'errors': [str(e)], 'proxies': added_proxies}
    finally:
        db.close()
