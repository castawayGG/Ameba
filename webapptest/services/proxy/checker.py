import asyncio
import time
from datetime import datetime, timezone
from telethon import TelegramClient, errors, functions
from telethon.sessions import StringSession
from core.config import Config
from models.proxy import Proxy
from core.database import SessionLocal
from core.logger import log

async def test_proxy(proxy: Proxy) -> tuple:
    """
    Тестирует один прокси, проверяя его работоспособность через Telegram API.
    Возвращает кортеж (success: bool, speed_ms: int or None, error_message: str or None).
    """
    start_time = time.time()
    
    # Формируем кортеж для Telethon
    import socks
    if proxy.type == 'socks5':
        proxy_type = socks.SOCKS5
    elif proxy.type == 'socks4':
        proxy_type = socks.SOCKS4
    else:
        proxy_type = socks.HTTP

    if proxy.username and proxy.password:
        proxy_tuple = (proxy_type, proxy.host, proxy.port, True, proxy.username, proxy.password)
    else:
        proxy_tuple = (proxy_type, proxy.host, proxy.port, False)

    client = TelegramClient(StringSession(), Config.TG_API_ID, Config.TG_API_HASH, proxy=proxy_tuple)
    try:
        await client.connect()
        # Пытаемся получить конфигурацию (не требует авторизации)
        await client(functions.help.GetConfigRequest())
        speed = int((time.time() - start_time) * 1000)
        return True, speed, None
    except errors.FloodWaitError as e:
        # Flood wait тоже считается успехом (прокси работает, но Telegram ограничивает)
        speed = int((time.time() - start_time) * 1000)
        return True, speed, f"Flood wait {e.seconds}s"
    except Exception as e:
        return False, None, str(e)
    finally:
        await client.disconnect()

async def check_proxy_task(proxy_id: int):
    """
    Фоновая задача для проверки одного прокси (вызывается из Celery или напрямую).
    Обновляет статус прокси в базе данных.
    """
    db = SessionLocal()
    try:
        proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()
        if not proxy:
            log.warning(f"Proxy {proxy_id} not found for checking")
            return

        success, speed, error = await test_proxy(proxy)
        
        proxy.status = 'working' if success else 'dead'
        proxy.last_check = datetime.now(timezone.utc)
        if speed:
            proxy.speed = speed
            # Обновляем среднюю скорость (экспоненциальное скользящее среднее)
            if proxy.avg_speed:
                proxy.avg_speed = (proxy.avg_speed * 0.7 + speed * 0.3)
            else:
                proxy.avg_speed = speed
        if error:
            proxy.last_error = error[:500]  # обрезаем до 500 символов
        db.commit()
        log.info(f"Proxy {proxy_id} checked: status={proxy.status}, speed={speed}ms")
    except Exception as e:
        log.error(f"Error checking proxy {proxy_id}: {e}")
    finally:
        db.close()

async def check_all_proxies_task():
    """
    Фоновая задача для проверки всех прокси (запускается по расписанию).
    """
    db = SessionLocal()
    try:
        proxies = db.query(Proxy).all()
        for proxy in proxies:
            # Запускаем проверку асинхронно, но не ждём завершения всех одновременно,
            # чтобы не перегружать систему. Можно использовать asyncio.gather с ограничением.
            # Для простоты здесь просто последовательно.
            await check_proxy_task(proxy.id)
            # Небольшая задержка между проверками
            await asyncio.sleep(1)
    finally:
        db.close()