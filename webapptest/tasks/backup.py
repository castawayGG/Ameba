from celery import shared_task
from services.backup.archiver import create_backup
from core.logger import log
import datetime

@shared_task
def create_automatic_backup():
    """
    Автоматическое создание бэкапа (запускается по расписанию).
    """
    try:
        backup_file = create_backup()
        log.info(f"Automatic backup created: {backup_file.name}")
        return {'success': True, 'file': backup_file.name}
    except Exception as e:
        log.error(f"Automatic backup failed: {e}")
        return {'success': False, 'error': str(e)}