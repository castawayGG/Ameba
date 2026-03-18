import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

class Config:
    # Application version (used for cache-busting static assets)
    APP_VERSION = os.getenv('APP_VERSION', '1.0.0')

    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-key-123')
    FLASK_ENV = os.getenv('FLASK_ENV', 'production')
    DEBUG = os.getenv('FLASK_DEBUG', '0').lower() in ('true', '1', 't')

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///data.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Redis
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

    # Telegram
    TG_API_ID = int(os.getenv('TG_API_ID', 0))
    TG_API_HASH = os.getenv('TG_API_HASH', '')

    # Admin (initial)
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD_HASH = os.getenv('ADMIN_PASSWORD_HASH', '')

    # Security
    IP_WHITELIST = [ip.strip() for ip in os.getenv('IP_WHITELIST', '').split(',') if ip.strip()]
    MAX_LOGIN_ATTEMPTS = int(os.getenv('MAX_LOGIN_ATTEMPTS', 5))
    RATE_LIMIT_DEFAULT = os.getenv('RATE_LIMIT_DEFAULT', '100 per minute')

    # Proxy (global)
    PROXY_ENABLED = os.getenv('PROXY_ENABLED', 'false').lower() == 'true'
    PROXY_TYPE = os.getenv('PROXY_TYPE', 'socks5')
    PROXY_HOST = os.getenv('PROXY_HOST')
    PROXY_PORT = int(os.getenv('PROXY_PORT', 0)) if os.getenv('PROXY_PORT') else None
    PROXY_USERNAME = os.getenv('PROXY_USERNAME')
    PROXY_PASSWORD = os.getenv('PROXY_PASSWORD')

    # Encryption
    SESSION_ENCRYPTION_KEY = os.getenv('SESSION_ENCRYPTION_KEY', '').encode('utf-8')

    # Celery
    CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', REDIS_URL)
    CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', REDIS_URL)

    # Telegram Bot Notifications (alerts on login events)
    NOTIFICATION_BOT_TOKEN = os.getenv('NOTIFICATION_BOT_TOKEN', '')
    NOTIFICATION_CHAT_ID = os.getenv('NOTIFICATION_CHAT_ID', '')

    # Configurable rate limits (Flask-Limiter format, e.g. "10 per minute")
    RATE_LIMIT_LOGIN = os.getenv('RATE_LIMIT_LOGIN', '10 per minute')
    RATE_LIMIT_CODE_SEND = os.getenv('RATE_LIMIT_CODE_SEND', '5 per minute')
    RATE_LIMIT_CODE_VERIFY = os.getenv('RATE_LIMIT_CODE_VERIFY', '10 per minute')
    RATE_LIMIT_API = os.getenv('RATE_LIMIT_API', '60 per minute')

    # Auto proxy loading: interval in hours for scheduled refresh
    PROXY_REFRESH_HOURS = int(os.getenv('PROXY_REFRESH_HOURS', 6))
    PROXY_AUTO_UPLOAD_MAX = int(os.getenv('PROXY_AUTO_UPLOAD_MAX', 1000))

    # Cloudflare Turnstile (captcha on landings)
    TURNSTILE_SITE_KEY = os.getenv('TURNSTILE_SITE_KEY', '')
    TURNSTILE_SECRET_KEY = os.getenv('TURNSTILE_SECRET_KEY', '')

    # AI generation (OpenAI / Claude)
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY', '')

    # Feature flags (can be overridden via PanelSettings in DB)
    AI_ENABLED = os.getenv('AI_ENABLED', 'false').lower() == 'true'
    CLOAKING_ENABLED = os.getenv('CLOAKING_ENABLED', 'false').lower() == 'true'
    DNS_ROTATION_ENABLED = os.getenv('DNS_ROTATION_ENABLED', 'false').lower() == 'true'

    # Sentry error tracking
    SENTRY_DSN = os.getenv('SENTRY_DSN', '')

    # Celery queue monitoring
    CELERY_QUEUE_ALERT_THRESHOLD = int(os.getenv('CELERY_QUEUE_ALERT_THRESHOLD', 100))

    # Paths
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    SESSIONS_DIR = os.path.join(BASE_DIR, 'sessions')
    LOGS_DIR = os.path.join(BASE_DIR, 'logs')
    BACKUPS_DIR = os.path.join(BASE_DIR, 'backups')
    MEDIA_DIR = os.path.join(BASE_DIR, 'media')

    # Создаём директории, если их нет
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    os.makedirs(MEDIA_DIR, exist_ok=True)