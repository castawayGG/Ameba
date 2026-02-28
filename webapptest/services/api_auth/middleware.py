"""API key authentication middleware."""
from functools import wraps
from datetime import datetime, timezone
from flask import request, jsonify
from core.logger import log


def require_api_key(f):
    """Decorator that checks for a valid API key in Authorization header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid Authorization header'}), 401
        raw_key = auth_header[7:].strip()
        try:
            from web.extensions import db
            from models.api_key import ApiKey
            key_obj = db.session.query(ApiKey).filter_by(key=raw_key, is_active=True).first()
            if not key_obj:
                return jsonify({'error': 'Invalid API key'}), 401
            now = datetime.now(timezone.utc)
            if key_obj.expires_at:
                exp = key_obj.expires_at
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp < now:
                    return jsonify({'error': 'API key expired'}), 401
            key_obj.last_used = now
            db.session.commit()
        except Exception as e:
            log.error(f"API key auth error: {e}")
            return jsonify({'error': 'Authentication error'}), 500
        return f(*args, **kwargs)
    return decorated
