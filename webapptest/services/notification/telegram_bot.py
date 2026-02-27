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