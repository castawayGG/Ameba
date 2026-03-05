"""
pending_deletes.py — In-memory soft-delete store with expiry.

When a user deletes an account or proxy, the actual deletion is
deferred for UNDO_TTL_SECONDS. During this window the client can
call the cancel endpoint to restore the item. After expiry the
item must be explicitly confirmed (the JS timer does this
automatically), or the background reaper removes it.
"""
import threading
import time
import uuid
from typing import Any, Callable, Optional

UNDO_TTL_SECONDS = 10  # seconds the user has to undo

_lock = threading.Lock()
# token -> {user_id, entity_type, entity_id, entity_data, expires_at, delete_fn}
_pending: dict[str, dict] = {}


def register_pending(
    user_id: int,
    entity_type: str,
    entity_id: Any,
    entity_data: dict,
    delete_fn: Callable,
) -> str:
    """
    Store a pending delete. Returns an opaque undo token.

    delete_fn: zero-argument callable that performs the actual deletion
               when called (already has entity_id in closure).
    """
    token = uuid.uuid4().hex
    with _lock:
        _pending[token] = {
            "user_id": user_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "entity_data": entity_data,
            "delete_fn": delete_fn,
            "expires_at": time.monotonic() + UNDO_TTL_SECONDS,
        }
    return token


def confirm_delete(token: str, user_id: int) -> Optional[str]:
    """
    Perform the actual deletion for the given token.
    Returns the entity_type on success, None if not found / wrong user.
    """
    with _lock:
        entry = _pending.pop(token, None)
    if entry is None:
        return None
    if entry["user_id"] != user_id:
        return None
    entry["delete_fn"]()
    return entry["entity_type"]


def cancel_delete(token: str, user_id: int) -> Optional[dict]:
    """
    Cancel the pending deletion and restore the item.
    Returns the stored entity_data on success, None otherwise.
    """
    with _lock:
        entry = _pending.pop(token, None)
    if entry is None:
        return None
    if entry["user_id"] != user_id:
        return None
    # Nothing to undo at DB level (item was never deleted); just remove from pending
    return entry["entity_data"]


def reap_expired(user_id: Optional[int] = None) -> int:
    """
    Execute and remove all expired pending deletes.
    If user_id is given, only reap for that user.
    Returns number of items reaped.
    """
    now = time.monotonic()
    expired = []
    with _lock:
        for token, entry in list(_pending.items()):
            if entry["expires_at"] <= now:
                if user_id is None or entry["user_id"] == user_id:
                    expired.append((token, entry))
    for token, entry in expired:
        with _lock:
            _pending.pop(token, None)
        try:
            entry["delete_fn"]()
        except Exception:
            pass
    return len(expired)
