"""
Задача для генерации и отправки плановых PDF/Excel-отчётов.

Блок 7: Интеграции и уведомления.
"""
from tasks.celery_app import celery_app
from core.logger import log


@celery_app.task(bind=True, name='tasks.generate_and_send_report')
def generate_and_send_report(self, report_type: str = 'summary', recipient_chat_id: str = None):
    """
    Генерирует отчёт и отправляет его через Telegram-бот.
    
    :param report_type: Тип отчёта ('summary', 'accounts', 'campaigns')
    :param recipient_chat_id: ID чата для отправки (если None — берётся из настроек)
    """
    from services.export.pdf_report import generate_summary_report, collect_report_stats
    from services.notification.telegram_bot import send_notification
    from core.config import Config
    import requests
    import io
    import datetime
    
    log.info(f"Generating scheduled report: {report_type}")
    
    try:
        stats = collect_report_stats()
        html_bytes = generate_summary_report(stats)
        
        # Отправляем уведомление с краткой сводкой
        acc = stats.get('accounts', {})
        msg = (
            f"📊 <b>Плановый отчёт Ameba</b>\n"
            f"Дата: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC\n\n"
            f"👤 Аккаунты: {acc.get('total', 0)} всего, {acc.get('active', 0)} активных\n"
            f"🚫 Заблокированных: {acc.get('banned', 0)}\n"
            f"📢 Кампании: {stats.get('campaigns', {}).get('total', 0)} всего\n"
            f"🔌 Прокси: {stats.get('proxies', {}).get('working', 0)} рабочих"
        )
        send_notification(msg, chat_id=recipient_chat_id)
        
        # Если настроен бот-токен — отправляем HTML-файл
        bot_token = getattr(Config, 'NOTIFICATION_BOT_TOKEN', None)
        chat_id = recipient_chat_id or getattr(Config, 'NOTIFICATION_CHAT_ID', None)
        if bot_token and chat_id:
            now_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M')
            filename = f"report_{now_str}.html"
            try:
                resp = requests.post(
                    f'https://api.telegram.org/bot{bot_token}/sendDocument',
                    data={'chat_id': chat_id, 'caption': f'📊 Отчёт Ameba {now_str}'},
                    files={'document': (filename, io.BytesIO(html_bytes), 'text/html')},
                    timeout=30,
                )
                if resp.status_code != 200:
                    log.warning(f"send report file failed: {resp.status_code}")
            except Exception as e:
                log.error(f"send report file error: {e}")
        
        log.info("Scheduled report generated and sent")
        return {'success': True}
    
    except Exception as e:
        log.error(f"generate_and_send_report error: {e}")
        self.retry(exc=e, countdown=300, max_retries=3)


@celery_app.task(name='tasks.send_excel_report')
def send_excel_report(recipient_chat_id: str = None):
    """
    Генерирует Excel-отчёт по аккаунтам и отправляет в Telegram.
    
    :param recipient_chat_id: ID чата (если None — берётся из настроек)
    """
    from services.export.excel import ExcelExporter
    from core.config import Config
    from core.database import SessionLocal
    from models.account import Account
    import requests
    import datetime
    
    log.info("Generating Excel accounts report")
    
    db = SessionLocal()
    try:
        accounts = db.query(Account).order_by(Account.created_at.desc()).limit(1000).all()
        excel_buf = ExcelExporter.export_accounts(accounts)
        
        bot_token = getattr(Config, 'NOTIFICATION_BOT_TOKEN', None)
        chat_id = recipient_chat_id or getattr(Config, 'NOTIFICATION_CHAT_ID', None)
        
        if bot_token and chat_id:
            now_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M')
            filename = f"accounts_{now_str}.xlsx"
            try:
                resp = requests.post(
                    f'https://api.telegram.org/bot{bot_token}/sendDocument',
                    data={'chat_id': chat_id, 'caption': f'📊 Отчёт аккаунтов {now_str}'},
                    files={'document': (filename, excel_buf, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
                    timeout=30,
                )
                if resp.status_code != 200:
                    log.warning(f"send excel failed: {resp.status_code}")
                    return {'success': False}
                return {'success': True}
            except Exception as e:
                log.error(f"send_excel_report error: {e}")
                return {'success': False, 'error': str(e)}
        else:
            log.warning("Bot not configured for Excel report")
            return {'success': False, 'error': 'Bot not configured'}
    finally:
        db.close()
