import asyncio
import time
from typing import Dict, Optional
from telethon import TelegramClient
from telethon.sessions import StringSession
from core.config import Config
from services.proxy.manager import get_proxy_for_request
from utils.encryption import decrypt_session_data
from core.logger import log

class ClientPool:
    """
    Пул клиентов Telethon для управления множеством аккаунтов.
    Позволяет повторно использовать клиентов, автоматически переподключаться,
    ограничивает максимальное количество одновременно активных клиентов.
    """
    def __init__(self, max_clients: int = 200):
        self._clients: Dict[str, TelegramClient] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._last_used: Dict[str, float] = {}
        self.max_clients = max_clients

    async def get_client(self, account_id: str, session_data: bytes = None, proxy=None) -> TelegramClient:
        """
        Получить клиента для аккаунта.
        Если клиент уже есть в пуле, возвращает его (предварительно проверяя соединение).
        Если нет, создаёт нового клиента, используя переданные session_data и прокси.
        """
        # Если клиент уже есть в пуле
        if account_id in self._clients:
            client = self._clients[account_id]
            self._last_used[account_id] = time.time()
            # Проверяем, не отключился ли клиент
            if not client.is_connected():
                try:
                    await client.connect()
                except Exception as e:
                    log.error(f"Failed to reconnect client {account_id}: {e}")
                    # Если не удалось переподключиться, удаляем клиент и создадим новый
                    await self.remove_client(account_id)
                    return await self.get_client(account_id, session_data, proxy)
            return client

        # Если достигнут лимит, удаляем самый старый неиспользуемый клиент
        if len(self._clients) >= self.max_clients:
            oldest = min(self._last_used, key=self._last_used.get)
            await self.remove_client(oldest)

        # Создаём нового клиента
        if session_data is None:
            # Новая сессия (без данных)
            client = TelegramClient(StringSession(), Config.TG_API_ID, Config.TG_API_HASH, proxy=proxy)
        else:
            # Существующая сессия – расшифровываем и загружаем
            decrypted = decrypt_session_data(session_data)
            client = TelegramClient(StringSession(decrypted), Config.TG_API_ID, Config.TG_API_HASH, proxy=proxy)

        try:
            await client.connect()
        except Exception as e:
            log.error(f"Failed to connect client for {account_id}: {e}")
            raise

        self._clients[account_id] = client
        self._last_used[account_id] = time.time()
        return client

    async def remove_client(self, account_id: str):
        """Удаляет клиента из пула и закрывает соединение."""
        if account_id in self._clients:
            try:
                await self._clients[account_id].disconnect()
            except Exception as e:
                log.warning(f"Error while disconnecting client {account_id}: {e}")
            del self._clients[account_id]
            if account_id in self._last_used:
                del self._last_used[account_id]

    async def close_all(self):
        """Закрывает всех клиентов в пуле (например, при завершении работы)."""
        for account_id in list(self._clients.keys()):
            await self.remove_client(account_id)

    def get_lock(self, account_id: str) -> asyncio.Lock:
        """
        Возвращает блокировку для аккаунта, чтобы избежать одновременных действий
        (например, отправки сообщений) с одним и тем же аккаунтом.
        """
        if account_id not in self._locks:
            self._locks[account_id] = asyncio.Lock()
        return self._locks[account_id]

    async def cleanup_old_clients(self, max_idle_seconds: int = 3600):
        """
        Удаляет клиентов, которые не использовались дольше указанного времени.
        Можно запускать периодически из фоновой задачи.
        """
        now = time.time()
        to_remove = []
        for account_id, last_used in self._last_used.items():
            if now - last_used > max_idle_seconds:
                to_remove.append(account_id)
        for account_id in to_remove:
            await self.remove_client(account_id)
        log.info(f"Cleaned up {len(to_remove)} idle clients")

# Глобальный экземпляр пула клиентов
client_pool = ClientPool(max_clients=200)