"""
web/routes/ws.py — WebSocket endpoints registration.

Call register_ws(sock) inside create_app() after Sock(app) is created,
so that each application factory invocation gets its own fresh Sock.
"""
import json
import queue


def register_ws(sock):
    """Register WebSocket routes on the given Sock instance."""

    KEEPALIVE_TIMEOUT = 25  # seconds between keepalive pings

    @sock.route('/ws/notifications')
    def ws_notifications(ws):
        """
        Persistent WebSocket connection for real-time notifications.

        Protocol (server → client):
          {"type": "notification", "unread": N, "notifications": [...]}
          {"type": "inbox_count",  "count": N}
          {"type": "notification_new", ...}
          {"type": "alert",        "message": "...", "level": "info|warning|error"}
          {"type": "ping"}
        """
        from flask_login import current_user
        from web.ws_manager import register, unregister

        if not current_user.is_authenticated:
            ws.send(json.dumps({"type": "error", "message": "Unauthorized"}))
            return

        user_id = current_user.id
        q = register(user_id)

        try:
            _send_initial_state(ws, user_id)
        except Exception:
            unregister(user_id, q)
            return

        try:
            while True:
                try:
                    data = q.get(timeout=KEEPALIVE_TIMEOUT)
                    ws.send(data)
                except queue.Empty:
                    ws.send(json.dumps({"type": "ping"}))
        except Exception:
            pass
        finally:
            unregister(user_id, q)


def _send_initial_state(ws, user_id: int) -> None:
    """Push the current notification list and inbox count on connect."""
    from web.extensions import db
    from models.notification import Notification
    from models.incoming_message import IncomingMessage
    from sqlalchemy import select, func, desc

    unread_count = db.session.execute(
        select(func.count(Notification.id)).filter(
            Notification.user_id == user_id,
            Notification.is_read == False,  # noqa: E712
        )
    ).scalar() or 0

    notifs = db.session.execute(
        select(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(desc(Notification.created_at))
        .limit(20)
    ).scalars().all()

    ws.send(json.dumps({
        "type": "notification",
        "unread": unread_count,
        "notifications": [
            {
                "id": n.id,
                "title": n.title,
                "message": n.message,
                "type": n.type,
                "category": n.category,
                "is_read": n.is_read,
                "related_url": n.related_url,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifs
        ],
    }))

    inbox_count = db.session.execute(
        select(func.count(IncomingMessage.id)).filter(
            IncomingMessage.is_read == False  # noqa: E712
        )
    ).scalar() or 0

    ws.send(json.dumps({"type": "inbox_count", "count": inbox_count}))
