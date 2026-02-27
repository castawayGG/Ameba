import asyncio
from datetime import datetime, timezone
from core.database import SessionLocal
from models.campaign import Campaign
from models.account import Account
from core.logger import log
from services.telegram.actions import send_bulk_messages


async def run_campaign_async(campaign_id: int) -> dict:
    """
    Executes a phishing campaign asynchronously.

    Iterates over all active Telegram accounts and sends the campaign
    message (with optional variations) to every target in the campaign's
    target list.  Updates campaign progress counters after each account
    batch and marks the campaign as 'completed' on success or 'paused' on
    error.

    Returns a summary dict with keys: sent, failed, status (or error).
    """
    db = SessionLocal()
    campaign = None
    try:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            log.error(f"Campaign {campaign_id} not found")
            return {'error': 'Campaign not found'}

        if campaign.status != 'running':
            log.warning(
                f"Campaign {campaign_id} is not in running state "
                f"(status={campaign.status})"
            )
            return {'error': f"Campaign is not running (status={campaign.status})"}

        # JSON columns are already deserialised by SQLAlchemy
        targets = campaign.target_list if isinstance(campaign.target_list, list) else []
        variations = campaign.variations if isinstance(campaign.variations, list) else []
        message = campaign.message_template

        accounts = db.query(Account).filter(Account.status == 'active').all()
        if not accounts:
            campaign.status = 'paused'
            db.commit()
            return {'error': 'No active accounts available'}

        total_sent = 0
        total_failed = 0

        for account in accounts:
            result = await send_bulk_messages(account.id, targets, message, variations)
            total_sent += result.get('sent', 0)
            total_failed += result.get('failed', 0)
            campaign.processed += len(targets)
            campaign.successful += result.get('sent', 0)
            campaign.failed += result.get('failed', 0)
            db.commit()

        campaign.status = 'completed'
        campaign.completed_at = datetime.now(timezone.utc)
        db.commit()

        log.info(
            f"Campaign {campaign_id} completed: "
            f"sent={total_sent}, failed={total_failed}"
        )
        return {'sent': total_sent, 'failed': total_failed, 'status': 'completed'}

    except Exception as e:
        log.error(f"Campaign {campaign_id} runner error: {e}")
        if campaign:
            campaign.status = 'paused'
            try:
                db.commit()
            except Exception:
                db.rollback()
        return {'error': str(e)}
    finally:
        db.close()