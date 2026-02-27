import random
import asyncio
from typing import Optional
from sqlalchemy.orm import Session
from models.proxy import Proxy
from core.database import SessionLocal
from core.logger import log

class ProxyManager:
    """
    Менеджер прокси.
    - Поддерживает кеш рабочих прокси.
    - Осуществляет ротацию прокси для каждого запроса.
    - Периодически обновляет кеш из базы данных.
    """
    def __init__(self):
        self._working_proxies: list[Proxy] = []
        self._last_refresh = 0
        self._refresh_interval = 300  # 5 минут

    async def get_proxy_for_request(self) -> Optional[tuple]:
        """
        Возвращает кортеж прокси для Telethon (или None, если нет рабочих прокси).
        Ротация: случайный выбор из списка рабочих прокси.
        """
        await self._refresh_cache_if_needed()
        if not self._working_proxies:
            return None
        proxy = random.choice(self._working_proxies)
        return self._to_telethon_tuple(proxy)

    async def _refresh_cache_if_needed(self):
        """Обновляет кеш, если истёк интервал обновления."""
        now = asyncio.get_running_loop().time()
        if now - self._last_refresh > self._refresh_interval:
            await self._refresh_cache()

    async def _refresh_cache(self):
        """Загружает список рабочих прокси из базы данных."""
        loop = asyncio.get_running_loop()
        # Выполняем запрос к БД в отдельном потоке, чтобы не блокировать event loop
        proxies = await loop.run_in_executor(None, self._fetch_working_proxies)
        self._working_proxies = proxies
        self._last_refresh = asyncio.get_running_loop().time()
        log.info(f"Proxy cache refreshed: {len(proxies)} working proxies")

    def _fetch_working_proxies(self) -> list[Proxy]:
        """Синхронный запрос к БД для получения рабочих прокси."""
        db = SessionLocal()
        try:
            proxies = db.query(Proxy).filter(
                Proxy.status == 'working',
                Proxy.enabled == True
            ).all()
            return proxies
        finally:
            db.close()

    def _to_telethon_tuple(self, proxy: Proxy) -> tuple:
        """Преобразует объект Proxy в кортеж, понятный Telethon."""
        import socks
        if proxy.type == 'socks5':
            proxy_type = socks.SOCKS5
        elif proxy.type == 'socks4':
            proxy_type = socks.SOCKS4
        else:
            proxy_type = socks.HTTP
        if proxy.username and proxy.password:
            return (proxy_type, proxy.host, proxy.port, True, proxy.username, proxy.password)
        return (proxy_type, proxy.host, proxy.port, False)

# Глобальный экземпляр менеджера прокси
proxy_manager = ProxyManager()

# Удобная функция для получения прокси (для использования в auth.py и других модулях)
async def get_proxy_for_request():
    return await proxy_manager.get_proxy_for_request()