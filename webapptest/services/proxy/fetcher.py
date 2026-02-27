# services/proxy/fetcher.py
# Сервис автоматической загрузки бесплатных прокси
import re
import requests
from typing import List, Dict
from core.logger import log


# Источники бесплатных прокси (публичные списки)
FREE_PROXY_SOURCES = [
    'https://www.proxy-list.download/api/v1/get?type=socks5',
    'https://www.proxy-list.download/api/v1/get?type=http',
]

# Резервный HTML-парсер для free-proxy-list.net
FREE_PROXY_LIST_URL = 'https://free-proxy-list.net/'


def fetch_free_proxies() -> List[Dict]:
    """
    Загружает список бесплатных прокси из нескольких источников.
    Возвращает список словарей {'type', 'host', 'port'}.
    """
    proxies = []

    # Источник 1: proxy-list.download (plain text, line per proxy)
    for url in FREE_PROXY_SOURCES:
        try:
            proxy_type = 'socks5' if 'socks5' in url else 'http'
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                for line in resp.text.strip().splitlines():
                    line = line.strip()
                    if ':' in line:
                        parts = line.split(':')
                        if len(parts) == 2:
                            host, port = parts
                            try:
                                proxies.append({
                                    'type': proxy_type,
                                    'host': host.strip(),
                                    'port': int(port.strip()),
                                })
                            except ValueError:
                                pass
        except requests.RequestException as e:
            log.warning(f"Failed to fetch proxies from {url}: {e}")

    # Источник 2: free-proxy-list.net (HTML парсинг через regex)
    try:
        resp = requests.get(FREE_PROXY_LIST_URL, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; ProxyChecker/1.0)'
        })
        if resp.status_code == 200:
            # Ищем строки таблицы: IP, Port, ...
            rows = re.findall(
                r'<tr><td>(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})</td><td>(\d{2,5})</td>',
                resp.text
            )
            for host, port in rows:
                try:
                    proxies.append({'type': 'http', 'host': host, 'port': int(port)})
                except ValueError:
                    pass
    except requests.RequestException as e:
        log.warning(f"Failed to fetch proxies from free-proxy-list.net: {e}")

    log.info(f"Fetched {len(proxies)} free proxies from sources")
    return proxies
