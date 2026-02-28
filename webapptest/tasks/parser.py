from tasks.celery_app import celery_app
from core.logger import log


@celery_app.task(bind=True, name='tasks.parser.run_parse_task')
def run_parse_task(self, task_id, account_id, group_link, filters=None):
    """Celery task wrapper for async parse_group_members."""
    import asyncio
    from services.telegram.parser import parse_group_members
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(parse_group_members(task_id, account_id, group_link, filters or {}))
    except Exception as e:
        log.error(f"run_parse_task error for task_id={task_id}: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=2)
    finally:
        loop.close()
