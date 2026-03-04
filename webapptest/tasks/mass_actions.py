from celery import shared_task
from services.telegram.actions import send_bulk_messages, join_group, change_account_password, enable_2fa
from core.database import SessionLocal
from models.account import Account
from models.campaign import Campaign
from core.logger import log
from datetime import datetime, timezone
import asyncio

@shared_task(bind=True, max_retries=3)
def send_bulk_messages_task(self, account_id: str, contacts: list, base_text: str, variations: list):
    try:
        return asyncio.run(send_bulk_messages(account_id, contacts, base_text, variations))
    except Exception as e:
        log.error(f"send_bulk_messages_task failed: {e}")
        self.retry(exc=e, countdown=60)

@shared_task(bind=True, max_retries=3)
def join_group_task(self, account_id: str, invite_link: str):
    try:
        success = asyncio.run(join_group(account_id, invite_link))
        return {'success': success}
    except Exception as e:
        log.error(f"join_group_task failed: {e}")
        self.retry(exc=e, countdown=60)

@shared_task(bind=True, max_retries=3)
def change_password_task(self, account_id: str, new_password: str):
    try:
        success = asyncio.run(change_account_password(account_id, new_password))
        return {'success': success}
    except Exception as e:
        log.error(f"change_password_task failed: {e}")
        self.retry(exc=e, countdown=60)

@shared_task(bind=True, max_retries=3)
def enable_2fa_task(self, account_id: str, password: str, hint: str):
    try:
        success = asyncio.run(enable_2fa(account_id, password, hint))
        return {'success': success}
    except Exception as e:
        log.error(f"enable_2fa_task failed: {e}")
        self.retry(exc=e, countdown=60)

@shared_task
def run_campaign(campaign_id: int):
    db = SessionLocal()
    campaign = None
    try:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign or campaign.status != 'running':
            return

        # JSON columns are already deserialised by SQLAlchemy; avoid double-decoding
        if not isinstance(campaign.target_list, list):
            log.warning(
                f"Campaign {campaign_id}: target_list is not a list "
                f"(type={type(campaign.target_list).__name__}), treating as empty"
            )
        targets = campaign.target_list if isinstance(campaign.target_list, list) else []
        if campaign.variations is not None and not isinstance(campaign.variations, list):
            log.warning(
                f"Campaign {campaign_id}: variations is not a list "
                f"(type={type(campaign.variations).__name__}), treating as empty"
            )
        variations = campaign.variations if isinstance(campaign.variations, list) else []
        message = campaign.message_template

        accounts = db.query(Account).filter(Account.status == 'active').all()

        for account in accounts:
            result = asyncio.run(send_bulk_messages(account.id, targets, message, variations))
            campaign.processed += len(targets)
            campaign.successful += result['sent']
            campaign.failed += result['failed']
            db.commit()

        # Корректное завершение кампании
        campaign.status = 'completed'
        campaign.completed_at = datetime.now(timezone.utc)
        db.commit()
        
    except Exception as e:
        log.error(f"run_campaign error for ID {campaign_id}: {e}")
        db.rollback()
        if campaign:
            campaign.status = 'paused'
            db.commit()
    finally:
        db.close()


@shared_task(bind=True, max_retries=1)
def start_warming_task(self, account_id: str, scenario_id: int):
    """Stub: warming task not yet fully implemented."""
    log.warning(f"start_warming_task not implemented (account={account_id}, scenario={scenario_id})")
    return {'success': False, 'error': 'not_implemented', 'account_id': account_id, 'scenario_id': scenario_id}


# ---------------------------------------------------------------------------
# MACRO EXECUTION
# ---------------------------------------------------------------------------

_SUPPORTED_MACRO_ACTIONS = {
    'assign_proxy',
    'remove_proxy',
    'set_status',
    'assign_tags',
    'send_message',
    'join_group',
}


@shared_task
def apply_macro_task(macro_id: int, account_ids: list):
    """
    Apply a saved macro (sequence of steps) to a list of account IDs.

    Each step is a dict: {"action": "<action_name>", "params": {...}}

    Supported actions:
      assign_proxy   – params: {proxy_id: int|null}
      remove_proxy   – params: {}
      set_status     – params: {status: str}
      assign_tags    – params: {tag_ids: [int, ...]}
      send_message   – params: {contacts: [str], text: str, variations: [str]}
      join_group     – params: {invite_link: str}
    """
    db = SessionLocal()
    op = None
    try:
        from models.macro import Macro
        from models.bulk_operation import BulkOperation
        from models.tag import Tag

        macro = db.query(Macro).filter(Macro.id == macro_id).first()
        if not macro:
            log.error(f"apply_macro_task: macro {macro_id} not found")
            return

        steps = macro.steps if isinstance(macro.steps, list) else []

        op = BulkOperation(
            operation_type=f'macro:{macro.name}',
            status='running',
            total=len(account_ids),
            params={'macro_id': macro_id, 'account_ids': account_ids},
            started_at=datetime.now(timezone.utc),
        )
        db.add(op)
        db.commit()

        errors = []
        succeeded = 0

        for acc_id in account_ids:
            acc = db.query(Account).filter(Account.id == acc_id).first()
            if not acc:
                errors.append({'id': acc_id, 'error': 'account not found'})
                continue
            try:
                for step in steps:
                    action = step.get('action')
                    params = step.get('params', {})

                    if action == 'assign_proxy':
                        acc.proxy_id = params.get('proxy_id')
                    elif action == 'remove_proxy':
                        acc.proxy_id = None
                    elif action == 'set_status':
                        acc.status = params.get('status', acc.status)
                    elif action == 'assign_tags':
                        tag_ids = params.get('tag_ids', [])
                        tags = db.query(Tag).filter(Tag.id.in_(tag_ids)).all()
                        acc.tags = tags
                    elif action == 'send_message':
                        contacts = params.get('contacts', [])
                        text = params.get('text', '')
                        variations = params.get('variations', [])
                        asyncio.run(send_bulk_messages(acc_id, contacts, text, variations))
                    elif action == 'join_group':
                        invite_link = params.get('invite_link', '')
                        asyncio.run(join_group(acc_id, invite_link))

                db.commit()
                succeeded += 1
            except Exception as step_err:
                db.rollback()
                errors.append({'id': acc_id, 'error': str(step_err)})

            op.processed += 1
            db.commit()

        op.succeeded = succeeded
        op.failed = len(errors)
        op.errors = errors
        op.status = 'completed'
        op.completed_at = datetime.now(timezone.utc)

        macro.runs_count += 1
        macro.last_run = datetime.now(timezone.utc)
        db.commit()

        log.info(f"apply_macro_task macro={macro_id} done: {succeeded}/{len(account_ids)} ok")
        return {'success': True, 'succeeded': succeeded, 'failed': len(errors)}

    except Exception as e:
        log.error(f"apply_macro_task error: {e}")
        db.rollback()
        if op:
            op.status = 'failed'
            try:
                db.commit()
            except Exception:
                pass
        return {'success': False, 'error': str(e)}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# CLOUD BACKUP
# ---------------------------------------------------------------------------

@shared_task
def cloud_backup_task(backup_filename: str):
    """Upload an existing local backup file to the configured cloud provider."""
    try:
        from services.backup.cloud import upload_backup
        from core.config import Config
        from pathlib import Path

        backup_path = Path(Config.BACKUPS_DIR) / backup_filename
        result = upload_backup(str(backup_path))
        log.info(f"cloud_backup_task success: {result}")
        return {'success': True, 'result': result}
    except Exception as e:
        log.error(f"cloud_backup_task failed: {e}")
        return {'success': False, 'error': str(e)}