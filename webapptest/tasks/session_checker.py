# tasks/session_checker.py
# Задачи Celery для проверки и восстановления сессий Telegram-аккаунтов
import asyncio
from celery import shared_task
from core.database import SessionLocal
from models.account import Account
from models.account_log import AccountLog
from core.logger import log
from datetime import datetime, timezone, timedelta


@shared_task(bind=True, max_retries=2, name='tasks.session_checker.check_all_sessions')
def check_all_sessions(self):
    """
    Массовая проверка валидности сессий всех аккаунтов.
    Обновляет статус аккаунта и записывает результат в AccountLog.
    """
    db = SessionLocal()
    try:
        accounts = db.query(Account).all()
        checked = 0
        errors = 0
        for account in accounts:
            try:
                result = asyncio.run(_check_single_session(account.id))
                # Обновляем статус и время последней проверки (объект уже получен выше)
                account.last_checked = datetime.now(timezone.utc)
                if result['valid']:
                    if result.get('reason') == 'flood_wait':
                        account.status = 'flood_wait'
                        flood_sec = result.get('flood_seconds', 0)
                        account.flood_wait_until = datetime.now(timezone.utc) + timedelta(seconds=flood_sec)
                        account.status_detail = f'Flood wait {flood_sec}s'
                    else:
                        if account.status in ('expired', 'inactive', 'flood_wait'):
                            account.status = 'active'
                        account.flood_wait_until = None
                        account.status_detail = None
                    # Обновляем расширенные поля
                    if result.get('premium') is not None:
                        account.premium = result['premium']
                    if result.get('dc_id'):
                        account.dc_id = result['dc_id']
                    if result.get('tg_id'):
                        account.tg_id = result['tg_id']
                    account.last_active = datetime.now(timezone.utc)
                else:
                    new_status = result.get('reason', 'inactive')
                    # Маппинг причин на статусы
                    status_map = {
                        'banned': 'banned',
                        'deactivated': 'banned',
                        '2fa_required': '2fa',
                        'session_expired': 'expired',
                    }
                    account.status = status_map.get(new_status, 'inactive')
                    account.status_detail = result.get('reason', '')
                db.commit()

                # Пишем лог действия над аккаунтом
                entry = AccountLog(
                    account_id=account.id,
                    action='check_session',
                    result='ok' if result['valid'] else 'error',
                    details=result.get('reason', 'valid') if not result['valid'] else 'session valid',
                    initiator='system',
                )
                db.add(entry)
                db.commit()
                checked += 1
            except Exception as e:
                log.error(f"Session check error for account {account.id}: {e}")
                errors += 1

        log.info(f"Session check complete: {checked} checked, {errors} errors")
        return {'checked': checked, 'errors': errors}
    finally:
        db.close()


@shared_task(bind=True, max_retries=3, name='tasks.session_checker.check_single_session')
def check_single_session_task(self, account_id: str, initiator: str = 'system', initiator_ip: str = None):
    """
    Проверка валидности сессии одного аккаунта.
    """
    db = SessionLocal()
    try:
        result = asyncio.run(_check_single_session(account_id))
        acc = db.query(Account).filter(Account.id == account_id).first()
        if acc:
            acc.last_checked = datetime.now(timezone.utc)
            if result['valid']:
                if result.get('reason') == 'flood_wait':
                    acc.status = 'flood_wait'
                    flood_sec = result.get('flood_seconds', 0)
                    acc.flood_wait_until = datetime.now(timezone.utc) + timedelta(seconds=flood_sec)
                    acc.status_detail = f'Flood wait {flood_sec}s'
                else:
                    if acc.status in ('expired', 'inactive', 'flood_wait'):
                        acc.status = 'active'
                    acc.flood_wait_until = None
                    acc.status_detail = None
                # Обновляем расширенные поля
                if result.get('premium') is not None:
                    acc.premium = result['premium']
                if result.get('dc_id'):
                    acc.dc_id = result['dc_id']
                if result.get('tg_id'):
                    acc.tg_id = result['tg_id']
                acc.last_active = datetime.now(timezone.utc)
            else:
                status_map = {
                    'banned': 'banned',
                    'deactivated': 'banned',
                    '2fa_required': '2fa',
                    'session_expired': 'expired',
                }
                new_status = result.get('reason', 'inactive')
                acc.status = status_map.get(new_status, 'inactive')
                acc.status_detail = result.get('reason', '')
            db.commit()

        entry = AccountLog(
            account_id=account_id,
            action='check_session',
            result='ok' if result['valid'] else 'error',
            details=result.get('reason', 'valid') if not result['valid'] else 'session valid',
            initiator=initiator,
            initiator_ip=initiator_ip,
        )
        db.add(entry)
        db.commit()
        return result
    except Exception as e:
        log.error(f"check_single_session_task error for {account_id}: {e}")
        self.retry(exc=e, countdown=30)
    finally:
        db.close()


@shared_task(bind=True, max_retries=2, name='tasks.session_checker.auto_relogin')
def auto_relogin_task(self, account_id: str, initiator: str = 'system'):
    """
    Попытка автоматической повторной авторизации аккаунта
    (для аккаунтов с истёкшей сессией).
    """
    db = SessionLocal()
    try:
        acc = db.query(Account).filter(Account.id == account_id).first()
        if not acc:
            return {'success': False, 'reason': 'account_not_found'}
        if acc.status not in ('expired', 'inactive'):
            return {'success': False, 'reason': 'not_expired'}

        # Попытка повторного входа через сохранённые данные сессии
        result = asyncio.run(_attempt_relogin(account_id))

        acc.last_checked = datetime.now(timezone.utc)
        if result.get('success'):
            acc.status = 'active'
        db.commit()

        entry = AccountLog(
            account_id=account_id,
            action='auto_relogin',
            result='ok' if result.get('success') else 'error',
            details=result.get('reason', ''),
            initiator=initiator,
        )
        db.add(entry)
        db.commit()
        return result
    except Exception as e:
        log.error(f"auto_relogin_task error for {account_id}: {e}")
        self.retry(exc=e, countdown=60)
    finally:
        db.close()


# ---- Асинхронные вспомогательные функции ----

async def _check_single_session(account_id: str) -> dict:
    """
    Подключается к Telegram с существующей сессией и проверяет её валидность.
    Возвращает {'valid': bool, 'reason': str, ...доп. данные}.
    """
    from telethon import errors as tg_errors
    try:
        from services.telegram.actions import get_telegram_client
        client = await get_telegram_client(account_id)
        if client is None:
            return {'valid': False, 'reason': 'no_session'}
        try:
            await client.connect()
            if not await client.is_user_authorized():
                return {'valid': False, 'reason': 'session_expired'}
            # Лёгкий запрос для проверки активности
            me = await client.get_me()
            if me is None:
                return {'valid': False, 'reason': 'session_expired'}
            return {
                'valid': True,
                'reason': 'ok',
                'username': getattr(me, 'username', None),
                'premium': getattr(me, 'premium', False),
                'dc_id': getattr(me, 'dc_id', None) if hasattr(me, 'dc_id') else None,
                'tg_id': str(me.id) if me.id else None,
            }
        except tg_errors.FloodWaitError as e:
            return {'valid': True, 'reason': 'flood_wait', 'flood_seconds': e.seconds}
        finally:
            await client.disconnect()
    except Exception as e:
        err = str(e).lower()
        if 'banned' in err or 'deactivated' in err:
            return {'valid': False, 'reason': 'banned'}
        if '2fa' in err or 'two' in err:
            return {'valid': False, 'reason': '2fa_required'}
        if 'flood' in err:
            import re
            seconds_match = re.search(r'(?:flood|wait)\D*(\d+)', str(e).lower())
            flood_sec = int(seconds_match.group(1)) if seconds_match else 0
            return {'valid': True, 'reason': 'flood_wait', 'flood_seconds': flood_sec}
        return {'valid': False, 'reason': str(e)[:100]}


async def _attempt_relogin(account_id: str) -> dict:
    """
    Попытка автоматического повторного входа.
    Возвращает {'success': bool, 'reason': str}.
    """
    try:
        from services.telegram.actions import get_telegram_client
        client = await get_telegram_client(account_id)
        if client is None:
            return {'success': False, 'reason': 'no_session_data'}
        try:
            await client.connect()
            if await client.is_user_authorized():
                return {'success': True, 'reason': 'already_authorized'}
            return {'success': False, 'reason': 'requires_code'}
        finally:
            await client.disconnect()
    except Exception as e:
        return {'success': False, 'reason': str(e)[:100]}
