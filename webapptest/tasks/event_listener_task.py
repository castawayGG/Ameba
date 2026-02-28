from celery import shared_task
from core.logger import log


@shared_task(bind=True, name='tasks.event_listener.run_event_listener')
def run_event_listener(self):
    """Запускает Event Listener как долгоживущую Celery-задачу."""
    import asyncio
    from services.telegram.event_listener import start_listener
    try:
        asyncio.run(start_listener())
    except Exception as e:
        log.error(f"Event listener crashed: {e}")
        raise
