"""
Utilities for converting between Telethon StringSession and SQLite .session files.
"""
import os
import sqlite3
import tempfile
import struct
import base64
from core.logger import log


def string_session_to_sqlite(session_string: str, output_path: str) -> bool:
    """
    Convert a Telethon StringSession to a native SQLite .session file.
    Returns True on success.
    """
    try:
        from telethon.sessions import StringSession, SQLiteSession
        # Create a temporary StringSession to parse the data
        ss = StringSession(session_string)
        # Create SQLite session at output path
        sqlite_session = SQLiteSession(os.path.splitext(output_path)[0])
        # Copy session data from StringSession to SQLiteSession
        sqlite_session.set_dc(ss.dc_id, ss.server_address, ss.port)
        sqlite_session.auth_key = ss.auth_key
        sqlite_session.save()
        return True
    except Exception as e:
        log.error(f"string_session_to_sqlite error: {e}")
        return False


def sqlite_session_to_string(session_path: str) -> str:
    """
    Convert a native Telethon SQLite .session file to StringSession string.
    Returns empty string on failure.
    """
    try:
        from telethon.sessions import SQLiteSession, StringSession
        from telethon.crypto import AuthKey
        # Load from SQLite
        path_no_ext = os.path.splitext(session_path)[0]
        sq = SQLiteSession(path_no_ext)
        # Export to StringSession
        ss = StringSession()
        ss.set_dc(sq.dc_id, sq.server_address, sq.port)
        ss.auth_key = sq.auth_key
        return ss.save()
    except Exception as e:
        log.error(f"sqlite_session_to_string error: {e}")
        return ''


def detect_session_format(data: bytes) -> str:
    """
    Detect if data is 'string' (base64 StringSession text) or 'sqlite' (SQLite db).
    SQLite files start with b'SQLite format 3\x00'.
    """
    if len(data) >= 16 and data[:16] == b'SQLite format 3\x00':
        return 'sqlite'
    return 'string'
