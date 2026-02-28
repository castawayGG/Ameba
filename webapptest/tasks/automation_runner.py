"""
Celery task for executing automation steps sequentially with delays.
"""
import time
import datetime
from celery import shared_task
from core.database import SessionLocal
from core.logger import log


@shared_task(bind=True)
def run_automation(self, automation_id: int, context: dict = None):
    """
    Execute an automation's steps sequentially.
    context: optional dict with trigger data (e.g. account_id)
    """
    db = SessionLocal()
    try:
        from models.automation import Automation
        auto = db.query(Automation).filter(Automation.id == automation_id).first()
        if not auto or not auto.is_active:
            return {'success': False, 'reason': 'not found or inactive'}

        steps = auto.steps or []
        ctx = context or {}
        log.info(f"Running automation {automation_id} '{auto.name}' with {len(steps)} steps")

        for i, step in enumerate(steps):
            action = step.get('action', '')
            params = step.get('params', {})
            delay_seconds = step.get('delay_seconds', 0)

            if delay_seconds > 0:
                log.info(f"Automation {automation_id} step {i}: waiting {delay_seconds}s")
                time.sleep(delay_seconds)

            try:
                _execute_step(action, params, ctx, db)
                log.info(f"Automation {automation_id} step {i} '{action}' completed")
            except Exception as e:
                log.error(f"Automation {automation_id} step {i} '{action}' failed: {e}")

        auto.runs_count = (auto.runs_count or 0) + 1
        auto.last_run = datetime.datetime.utcnow()
        db.commit()
        return {'success': True, 'automation_id': automation_id}
    except Exception as e:
        log.error(f"run_automation error for id={automation_id}: {e}")
        return {'success': False, 'error': str(e)}
    finally:
        db.close()


def _execute_step(action: str, params: dict, ctx: dict, db) -> None:
    """Execute a single automation step action."""
    account_id = ctx.get('account_id')

    if action == 'wait':
        # Support both 'seconds' (params key) and 'delay_seconds' (step-level key)
        seconds = params.get('seconds', params.get('delay_seconds', 0))
        if seconds > 0:
            time.sleep(seconds)

    elif action == 'add_tag':
        if account_id:
            from models.tag import Tag, account_tags
            tag_name = params.get('tag_name', '')
            tag = db.query(Tag).filter(Tag.name == tag_name).first()
            if not tag:
                tag = Tag(name=tag_name)
                db.add(tag)
                db.flush()
            from sqlalchemy import text
            db.execute(
                text('INSERT OR IGNORE INTO account_tags (account_id, tag_id) VALUES (:aid, :tid)'),
                {'aid': account_id, 'tid': tag.id}
            )
            db.commit()

    elif action == 'start_warming':
        if account_id:
            scenario_id = params.get('scenario_id')
            if scenario_id:
                try:
                    from tasks.mass_actions import start_warming_task
                    start_warming_task.delay(account_id, scenario_id)
                except Exception as e:
                    log.warning(f"start_warming step error: {e}")

    elif action == 'send_message':
        if account_id:
            recipient = params.get('recipient', '')
            text_msg = params.get('text', '')
            if recipient and text_msg:
                try:
                    import asyncio
                    from services.telegram.actions import send_message
                    asyncio.run(send_message(account_id, recipient, text_msg))
                except Exception as e:
                    log.warning(f"send_message step error: {e}")

    elif action == 'join_group':
        if account_id:
            invite_link = params.get('invite_link', '')
            if invite_link:
                try:
                    import asyncio
                    from services.telegram.actions import join_group
                    asyncio.run(join_group(account_id, invite_link))
                except Exception as e:
                    log.warning(f"join_group step error: {e}")

    elif action == 'notify':
        text_msg = params.get('text', '')
        if text_msg:
            try:
                from services.notification.telegram_bot import send_notification
                send_notification(text_msg)
            except Exception as e:
                log.warning(f"notify step error: {e}")

    else:
        log.warning(f"Unknown automation action: {action}")
