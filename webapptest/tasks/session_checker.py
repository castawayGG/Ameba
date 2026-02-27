# tasks/session_checker.py
# Celery-задачи для проверки состояния сессий аккаунтов Telegram
from celery import shared_task
from core.database import SessionLocal
from core.logger import log
from models.account import Account
from models.account_activity_log import AccountActivityLog
from datetime import datetime, timezone


@shared_task(bind=True, max_retries=2)
def check_session_task(self, account_id: str):
    """
    Проверяет валидность сессии одного аккаунта Telegram.
    Обновляет health_status аккаунта и пишет запись в журнал активности.
    """
    db = SessionLocal()
    try:
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return {'success': False, 'error': 'Account not found'}

        health = _check_account_health(account)

        account.health_status = health
        account.last_checked = datetime.now(timezone.utc)

        # Записываем результат проверки в журнал активности
        log_entry = AccountActivityLog(
            account_id=account_id,
            action='session_check',
            result='success' if health == 'active' else 'warning',
            details=f'health_status={health}',
            initiator='celery',
        )
        db.add(log_entry)
        db.commit()
        log.info(f"Session check for {account.phone}: {health}")
        return {'success': True, 'account_id': account_id, 'health': health}
    except Exception as e:
        db.rollback()
        log.error(f"check_session_task failed for {account_id}: {e}")
        self.retry(exc=e, countdown=60)
    finally:
        db.close()


@shared_task
def check_all_sessions():
    """
    Массовая проверка всех аккаунтов (запускает отдельные задачи).
    Используется как периодическая задача в Celery Beat.
    """
    db = SessionLocal()
    try:
        accounts = db.query(Account).all()
        for acc in accounts:
            check_session_task.delay(acc.id)
        log.info(f"Scheduled session checks for {len(accounts)} accounts")
        return {'started': len(accounts)}
    finally:
        db.close()


@shared_task(bind=True, max_retries=3)
def auto_relogin_task(self, account_id: str):
    """
    Попытка автоматической реавторизации аккаунта с истёкшей сессией.
    На данном этапе только обновляет статус и пишет лог — полная реализация
    реавторизации требует интерактивного ввода кода и не может быть полностью
    автоматизирована без дополнительного сервиса.
    """
    db = SessionLocal()
    try:
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return {'success': False, 'error': 'Account not found'}

        log.info(f"Auto re-login attempt for account {account.phone}")

        # Записываем попытку реавторизации
        log_entry = AccountActivityLog(
            account_id=account_id,
            action='auto_relogin',
            result='warning',
            details='Auto re-login initiated; manual code confirmation may be required',
            initiator='celery',
        )
        db.add(log_entry)
        account.health_status = 'expired'
        db.commit()
        return {'success': True, 'account_id': account_id, 'status': 'relogin_initiated'}
    except Exception as e:
        db.rollback()
        log.error(f"auto_relogin_task failed for {account_id}: {e}")
        self.retry(exc=e, countdown=120)
    finally:
        db.close()


def _check_account_health(account: Account) -> str:
    """
    Определяет health_status аккаунта на основе поля status и наличия session_data.
    Возвращает: active, 2fa, banned, expired, invalid
    """
    if not account.session_data:
        return 'invalid'
    status = (account.status or '').lower()
    if status in ('banned', 'banned_perm'):
        return 'banned'
    if status in ('2fa', 'needs_2fa'):
        return '2fa'
    if status in ('expired', 'session_expired'):
        return 'expired'
    if status == 'active':
        return 'active'
    # Fallback: если session_data есть, считаем активным
    return 'active'
