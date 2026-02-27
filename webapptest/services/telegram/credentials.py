# services/telegram/credentials.py
# Менеджер учётных данных Telegram API с поддержкой ротации
import random
from datetime import datetime, timezone
from core.logger import log


def get_active_credential() -> dict:
    """
    Возвращает случайно выбранную активную пару API ID/Hash.
    Сначала пытается взять из базы данных (таблица api_credentials).
    Если таблица пуста или недоступна — использует Config.
    """
    try:
        from core.database import SessionLocal
        from models.api_credential import ApiCredential
        db = SessionLocal()
        try:
            creds = db.query(ApiCredential).filter_by(enabled=True).all()
            if creds:
                cred = random.choice(creds)
                # Обновляем счётчик использования
                cred.requests_count = (cred.requests_count or 0) + 1
                cred.last_used = datetime.now(timezone.utc)
                db.commit()
                return {'api_id': int(cred.api_id), 'api_hash': cred.api_hash}
        finally:
            db.close()
    except Exception as e:
        log.warning(f"credentials: cannot fetch from DB, falling back to Config: {e}")

    # Fallback: читаем из JSON-файла настроек или из Config
    try:
        import json
        from pathlib import Path
        from core.config import Config
        settings_file = Path(Config.BASE_DIR) / 'api_settings.json'
        if settings_file.exists():
            with open(settings_file) as f:
                s = json.load(f)
            api_id = int(s.get('api_id') or Config.TG_API_ID or 0)
            api_hash = s.get('api_hash') or Config.TG_API_HASH or ''
            if api_id and api_hash:
                return {'api_id': api_id, 'api_hash': api_hash}
    except Exception:
        pass

    from core.config import Config
    return {'api_id': Config.TG_API_ID, 'api_hash': Config.TG_API_HASH}
