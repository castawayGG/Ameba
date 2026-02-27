from celery import shared_task
from core.database import SessionLocal
from models.admin_log import AdminLog
from models.stat import Stat
from datetime import datetime, timedelta, timezone
from core.logger import log

@shared_task
def cleanup_old_logs(days: int = 30):
    """
    Удаляет логи администраторов старше указанного количества дней.
    """
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        deleted = db.query(AdminLog).filter(AdminLog.timestamp < cutoff).delete()
        db.commit()
        log.info(f"Cleaned up {deleted} old admin logs")
        return {'deleted': deleted}
    except Exception as e:
        log.error(f"Cleanup failed: {e}")
        return {'error': str(e)}
    finally:
        db.close()

@shared_task
def cleanup_old_stats(days: int = 90):
    """
    Оставляет только агрегированные данные, удаляет детальные записи статистики старше N дней.
    (Если используется детальное логирование, здесь можно удалять сырые записи)
    """
    # Здесь можно реализовать удаление старых записей из таблиц визитов, если они есть
    pass