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