import requests
from core.config import Config
from core.logger import log


def send_notification(message: str, chat_id: str = None) -> bool:
    """
    Sends a notification message via the Telegram Bot API.
    Requires NOTIFICATION_BOT_TOKEN and NOTIFICATION_CHAT_ID to be set in .env.
    Returns True on success, False otherwise.
    """
    bot_token = getattr(Config, 'NOTIFICATION_BOT_TOKEN', None)
    target_chat = chat_id or getattr(Config, 'NOTIFICATION_CHAT_ID', None)

    if not bot_token or not target_chat:
        log.warning(
            "Telegram notification is not configured "
            "(NOTIFICATION_BOT_TOKEN or NOTIFICATION_CHAT_ID missing)"
        )
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': target_chat,
        'text': message,
        'parse_mode': 'HTML',
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            log.info(f"Notification sent to chat {target_chat}")
            return True
        log.error(
            f"Telegram notification failed: HTTP {resp.status_code} – {resp.text}"
        )
        return False
    except requests.RequestException as e:
        log.error(f"Telegram notification request error: {e}")
        return False


# ── Alert type constants ──
ALERT_ACCOUNT_BAN = 'ban'
ALERT_PROXY_DOWN = 'proxy'
ALERT_INCOMING_LEAD = 'lead'
ALERT_CAMPAIGN_DONE = 'campaign'
ALERT_FLOOD_WAIT = 'flood'


def _get_pref_key(alert_type: str, channel: str) -> str:
    """Return the notification_prefs key for a given alert type and channel."""
    return f'{alert_type}_{channel}'


def send_alert(alert_type: str, message: str, db=None) -> None:
    """
    Send an alert of a given type to all users who have opted in via their
    notification_prefs.  Supports channels:
      - 'telegram': use per-user tg_bot_token + tg_chat_id stored in prefs,
                    falling back to global NOTIFICATION_BOT_TOKEN / NOTIFICATION_CHAT_ID
      - 'panel':    create an in-app Notification record for the user

    :param alert_type: one of ALERT_* constants (e.g. 'ban', 'proxy', 'lead', 'campaign')
    :param message:    HTML message text
    :param db:         SQLAlchemy db session (optional; if None, global config is used)
    """
    if db is None:
        # No DB access: fall back to global notification
        send_notification(message)
        return

    try:
        from models.user import User
        from models.notification import Notification
        from sqlalchemy import select

        users = db.execute(select(User).filter_by(is_active=True)).scalars().all()
        for user in users:
            prefs = user.notification_prefs or {}

            # Panel notification
            panel_key = _get_pref_key(alert_type, 'panel')
            if prefs.get(panel_key, False):
                try:
                    notif = Notification(
                        user_id=user.id,
                        title=f'Алерт: {alert_type}',
                        message=message,
                        type='warning' if alert_type in (ALERT_ACCOUNT_BAN, ALERT_PROXY_DOWN) else 'info',
                        category='system',
                    )
                    db.add(notif)
                except Exception as e:
                    log.error(f"send_alert panel error for user {user.id}: {e}")

            # Telegram notification
            tg_key = _get_pref_key(alert_type, 'telegram')
            if prefs.get(tg_key, False):
                bot_token = user.tg_bot_token or getattr(Config, 'NOTIFICATION_BOT_TOKEN', None)
                chat_id = user.tg_chat_id or getattr(Config, 'NOTIFICATION_CHAT_ID', None)
                if bot_token and chat_id:
                    _send_telegram_raw(message, bot_token, chat_id)

        db.commit()
    except Exception as e:
        log.error(f"send_alert error: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        # Fall back to global notification
        send_notification(message)


def _send_telegram_raw(message: str, bot_token: str, chat_id: str) -> bool:
    """Low-level Telegram sendMessage call."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(url, json={
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML',
        }, timeout=10)
        return resp.status_code == 200
    except requests.RequestException as e:
        log.error(f"_send_telegram_raw error: {e}")
        return False
