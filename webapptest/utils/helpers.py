import re
import random
import string
from datetime import datetime, timezone


def generate_random_id(length: int = 32) -> str:
    """Generates a random alphanumeric ID of the given length."""
    chars = string.ascii_lowercase + string.digits
    return ''.join(random.choices(chars, k=length))


def truncate_text(text: str, max_length: int = 100, suffix: str = '...') -> str:
    """Truncates text to max_length characters, appending suffix if truncated."""
    if not text or len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def format_bytes(size: int) -> str:
    """Converts a byte count to a human-readable string (e.g. '1.2 MB')."""
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def sanitize_phone(phone: str) -> str:
    """Strips all non-digit characters from a phone number string."""
    return re.sub(r'\D', '', phone)


def utcnow() -> datetime:
    """Returns the current UTC datetime as a timezone-aware object."""
    return datetime.now(timezone.utc)