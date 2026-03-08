import asyncio
import time
from collections import OrderedDict
from telethon import TelegramClient
from telethon.sessions import StringSession
from core.config import Config
from services.proxy.manager import get_proxy_for_request
from utils.encryption import decrypt_session_data
from core.logger import log

# Idle timeout after which an unused client is automatically disconnected (10 minutes)
_IDLE_TIMEOUT_SECONDS = 600


class ClientPool:
    """
    LRU-пул клиентов Telethon для управления множеством аккаунтов.
    Хранит активные клиенты в OrderedDict (LRU-порядок).
    Клиенты, неактивные более 10 минут, автоматически отключаются.
    """
    def __init__(self, max_clients: int = 200):
        self._clients: OrderedDict[str, TelegramClient] = OrderedDict()
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_used: dict[str, float] = {}
        self.max_clients = max_clients

    async def get_client(self, account_id: str, session_data: bytes = None, proxy=None) -> TelegramClient:
        """
        Получить клиента для аккаунта (LRU-стратегия вытеснения).
        Если клиент уже есть в пуле, переносит его в конец (как недавно использованный)
        и возвращает его. Если нет — создаёт нового клиента.
        """
        # Вытесняем клиентов, превысивших порог бездействия
        await self.cleanup_old_clients(_IDLE_TIMEOUT_SECONDS)

        if account_id in self._clients:
            # Перемещаем в конец для LRU-порядка
            self._clients.move_to_end(account_id)
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

        # Если достигнут лимит, вытесняем наименее недавно использованный (первый в OrderedDict)
        if len(self._clients) >= self.max_clients:
            oldest = next(iter(self._clients))
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
        """Удаляет клиента из пула и закрывает соединение.

        Блокировка (lock) удаляется вместе с клиентом: если вызывающий код
        владеет блокировкой, он должен освободить её до вызова remove_client,
        либо не вызывать get_client с тем же account_id после освобождения.
        """
        if account_id in self._clients:
            try:
                await self._clients[account_id].disconnect()
            except Exception as e:
                log.warning(f"Error while disconnecting client {account_id}: {e}")
            del self._clients[account_id]
            self._last_used.pop(account_id, None)
            # Remove the lock only if it is not currently acquired to avoid
            # silently dropping a lock held by concurrent code.
            lock = self._locks.get(account_id)
            if lock is not None and not lock.locked():
                del self._locks[account_id]

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

    async def cleanup_old_clients(self, max_idle_seconds: int = _IDLE_TIMEOUT_SECONDS):
        """
        Удаляет клиентов, которые не использовались дольше указанного времени.
        Вызывается автоматически при каждом обращении к get_client,
        а также может запускаться периодически из фоновой задачи.
        """
        now = time.time()
        to_remove = [
            account_id for account_id, last_used in self._last_used.items()
            if now - last_used > max_idle_seconds
        ]
        for account_id in to_remove:
            await self.remove_client(account_id)
        if to_remove:
            log.info(f"LRU client pool: evicted {len(to_remove)} idle client(s)")

# Глобальный экземпляр пула клиентов
client_pool = ClientPool(max_clients=200)