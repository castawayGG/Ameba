import random
import datetime
from core.database import SessionLocal
from models.cooldown import CooldownRule, CooldownLog
from core.logger import log


def get_rule(action_type):
    """Get active cooldown rule for an action type."""
    db = SessionLocal()
    try:
        return db.query(CooldownRule).filter_by(action_type=action_type, is_active=True).first()
    finally:
        db.close()


def get_random_delay(action_type):
    """Return a random delay (in seconds) for the action type."""
    rule = get_rule(action_type)
    if not rule:
        return 0
    return random.randint(rule.min_delay, rule.max_delay)


def can_perform_action(account_id, action_type):
    """
    Check if account can perform an action now.
    Returns (bool, wait_seconds).
    """
    db = SessionLocal()
    try:
        rule = db.query(CooldownRule).filter_by(action_type=action_type, is_active=True).first()
        if not rule:
            return True, 0

        now = datetime.datetime.utcnow()
        one_hour_ago = now - datetime.timedelta(hours=1)
        one_day_ago = now - datetime.timedelta(days=1)
        burst_window = now - datetime.timedelta(minutes=5)

        # Count actions in last hour
        hour_count = db.query(CooldownLog).filter(
            CooldownLog.account_id == account_id,
            CooldownLog.action_type == action_type,
            CooldownLog.performed_at >= one_hour_ago,
        ).count()

        if hour_count >= rule.max_per_hour:
            return False, rule.max_delay

        # Count actions in last day
        day_count = db.query(CooldownLog).filter(
            CooldownLog.account_id == account_id,
            CooldownLog.action_type == action_type,
            CooldownLog.performed_at >= one_day_ago,
        ).count()

        if day_count >= rule.max_per_day:
            return False, rule.burst_cooldown

        # Check burst
        burst_count = db.query(CooldownLog).filter(
            CooldownLog.account_id == account_id,
            CooldownLog.action_type == action_type,
            CooldownLog.performed_at >= burst_window,
        ).count()

        if burst_count >= rule.burst_limit:
            return False, rule.burst_cooldown

        return True, 0
    finally:
        db.close()


def record_action(account_id, action_type, delay_applied=0, was_throttled=False):
    """Record an action in the cooldown log."""
    db = SessionLocal()
    try:
        entry = CooldownLog(
            account_id=account_id,
            action_type=action_type,
            delay_applied=delay_applied,
            was_throttled=was_throttled,
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        db.rollback()
        log.error(f"record_action error: {e}")
    finally:
        db.close()


def get_account_stats(account_id):
    """Return action counts for an account in the last hour and day."""
    db = SessionLocal()
    try:
        now = datetime.datetime.utcnow()
        one_hour_ago = now - datetime.timedelta(hours=1)
        one_day_ago = now - datetime.timedelta(days=1)

        hour_count = db.query(CooldownLog).filter(
            CooldownLog.account_id == account_id,
            CooldownLog.performed_at >= one_hour_ago,
        ).count()

        day_count = db.query(CooldownLog).filter(
            CooldownLog.account_id == account_id,
            CooldownLog.performed_at >= one_day_ago,
        ).count()

        throttled_count = db.query(CooldownLog).filter(
            CooldownLog.account_id == account_id,
            CooldownLog.was_throttled == True,
            CooldownLog.performed_at >= one_day_ago,
        ).count()

        return {
            'hour': hour_count,
            'day': day_count,
            'throttled_day': throttled_count,
        }
    finally:
        db.close()


def reset_account_limits(account_id):
    """Delete all cooldown logs for an account (reset limits)."""
    db = SessionLocal()
    try:
        db.query(CooldownLog).filter(CooldownLog.account_id == account_id).delete()
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        log.error(f"reset_account_limits error: {e}")
        return False
    finally:
        db.close()
