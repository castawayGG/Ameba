import re
from pathlib import Path
from core.config import Config
from core.logger import log


def _session_basename(identifier: str) -> str:
    safe = re.sub(r'[^0-9A-Za-z_-]+', '_', identifier or '')
    safe = safe.strip('_')
    return (safe or 'session') + '.session'


def save_session_file(identifier: str, session_string: str) -> str:
    """Persist session_string to .session file in the configured directory."""
    filename = _session_basename(identifier)
    primary_dir = Path(Config.SESSIONS_DIR)
    legacy_dir = Path(getattr(Config, 'LEGACY_SESSIONS_DIR', Config.SESSIONS_DIR))

    primary_dir.mkdir(parents=True, exist_ok=True)
    path = primary_dir / filename
    path.write_text(session_string or '', encoding='utf-8')

    if legacy_dir != primary_dir:
        try:
            legacy_dir.mkdir(parents=True, exist_ok=True)
            (legacy_dir / filename).write_text(session_string or '', encoding='utf-8')
        except Exception as exc:  # pragma: no cover - best-effort mirror
            log.warning(f"Failed to mirror session file to legacy dir: {exc}")

    return str(path)


def find_session_file(identifier: str):
    """Locate a saved .session file by identifier, checking both new and legacy dirs."""
    filename = _session_basename(identifier)
    primary_path = Path(Config.SESSIONS_DIR) / filename
    if primary_path.exists():
        return primary_path

    legacy_dir = Path(getattr(Config, 'LEGACY_SESSIONS_DIR', Config.SESSIONS_DIR))
    legacy_path = legacy_dir / filename
    if legacy_path.exists():
        return legacy_path
    return None
