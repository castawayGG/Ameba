"""
ws_manager.py — In-process WebSocket broadcast helper.

Each connected WebSocket client registers a Queue. When
create_notification() or another event fires, it calls
broadcast_to_user() to push a JSON string into the user's
queues so that the WebSocket handler can forward it to the browser.
"""
import queue
import threading
import json

_lock = threading.Lock()
# user_id (int) -> list of Queue instances (one per open WS tab)
_connections: dict[int, list[queue.Queue]] = {}


def register(user_id: int) -> queue.Queue:
    """Register a new WebSocket connection for user_id. Returns a Queue."""
    q: queue.Queue = queue.Queue(maxsize=64)
    with _lock:
        if user_id not in _connections:
            _connections[user_id] = []
        _connections[user_id].append(q)
    return q


def unregister(user_id: int, q: queue.Queue) -> None:
    """Remove a closed WebSocket connection."""
    with _lock:
        if user_id in _connections:
            _connections[user_id] = [x for x in _connections[user_id] if x is not q]
            if not _connections[user_id]:
                del _connections[user_id]


def broadcast_to_user(user_id: int, event_type: str, payload: dict) -> None:
    """Push an event to all open WebSocket tabs for the given user."""
    data = json.dumps({"type": event_type, **payload})
    with _lock:
        queues = list(_connections.get(user_id, []))
    for q in queues:
        try:
            q.put_nowait(data)
        except queue.Full:
            pass


def broadcast_to_all(event_type: str, payload: dict) -> None:
    """Push an event to every connected user (e.g. system alerts)."""
    data = json.dumps({"type": event_type, **payload})
    with _lock:
        all_queues = [q for qs in _connections.values() for q in qs]
    for q in all_queues:
        try:
            q.put_nowait(data)
        except queue.Full:
            pass
