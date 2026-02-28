"""Async webhook dispatcher with retry logic."""
import hashlib
import hmac
import json
import time
import threading
import requests
from datetime import datetime, timezone
from core.logger import log


def _sign_payload(secret: str, payload: bytes) -> str:
    """Compute HMAC-SHA256 signature for webhook payload."""
    return hmac.new(key=secret.encode('utf-8'), msg=payload, digestmod=hashlib.sha256).hexdigest()


def _send_webhook(webhook_id: int, event_type: str, payload: dict, app):
    """Send a single webhook delivery attempt (runs in background thread)."""
    with app.app_context():
        from web.extensions import db
        from models.webhook import Webhook, WebhookDelivery

        webhook = db.session.get(Webhook, webhook_id)
        if not webhook or not webhook.is_active:
            return

        payload_bytes = json.dumps(payload, default=str).encode('utf-8')
        headers = {
            'Content-Type': 'application/json',
            'X-Webhook-Event': event_type,
        }
        if webhook.secret:
            headers['X-Webhook-Signature'] = _sign_payload(webhook.secret, payload_bytes)

        success = False
        response_code = None
        response_body = None

        for attempt in range(max(1, webhook.retry_count)):
            try:
                resp = requests.post(
                    webhook.url,
                    data=payload_bytes,
                    headers=headers,
                    timeout=10,
                )
                response_code = resp.status_code
                response_body = resp.text[:500]
                success = 200 <= resp.status_code < 300
                if success:
                    break
            except Exception as e:
                response_body = str(e)[:500]
                log.warning(f"Webhook {webhook_id} attempt {attempt+1} failed: {e}")
            if attempt < webhook.retry_count - 1:
                time.sleep(2 ** attempt)  # exponential backoff

        delivery = WebhookDelivery(
            webhook_id=webhook_id,
            event_type=event_type,
            payload=payload,
            response_code=response_code,
            response_body=response_body,
            success=success,
        )
        webhook.last_triggered = datetime.now(timezone.utc)
        db.session.add(delivery)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            log.error(f"Webhook delivery DB error: {e}")


def dispatch_event(event_type: str, payload: dict, app=None):
    """
    Dispatch a webhook event to all active webhooks subscribed to that event.
    Runs each delivery in a background thread.
    """
    if app is None:
        try:
            from flask import current_app
            app = current_app._get_current_object()
        except RuntimeError:
            log.warning("dispatch_event called outside Flask context without app")
            return

    try:
        from web.extensions import db
        from models.webhook import Webhook
        with app.app_context():
            webhooks = db.session.query(Webhook).filter_by(is_active=True).all()
            for wh in webhooks:
                events = wh.events or []
                if event_type in events or '*' in events:
                    t = threading.Thread(
                        target=_send_webhook,
                        args=(wh.id, event_type, payload, app),
                        daemon=True,
                    )
                    t.start()
    except Exception as e:
        log.error(f"dispatch_event error: {e}")
