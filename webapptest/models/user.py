from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base
import bcrypt
import pyotp
from datetime import datetime, timezone

# All configurable permission keys
ALL_PERMISSIONS = [
    'view_proxies',
    'delete_accounts',
    'run_campaigns',
    'view_logs',
    'manage_webhooks',
    'manage_api_keys',
    'manage_users',
]

class User(Base):
    """
    Модель пользователя (администратора) системы.
    Поддерживает аутентификацию, хеширование паролей и 2FA.
    """
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    otp_secret = Column(String(32), nullable=True)
    is_active = Column(Boolean, default=True)
    role = Column(String(20), default='admin')  # admin, superadmin, viewer
    created_at = Column(DateTime, server_default=func.now())
    last_login = Column(DateTime, nullable=True)
    login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    theme = Column(String(20), default='dark-blue')
    # Granular permissions (JSON dict: {perm_key: bool}). Null = all defaults apply.
    permissions = Column(JSON, nullable=True)
    # Per-user notification preferences
    notification_prefs = Column(JSON, nullable=True)
    # Per-user Telegram bot settings for alerts
    tg_bot_token = Column(String(200), nullable=True)
    tg_chat_id = Column(String(100), nullable=True)
    # UI language preference ('ru' or 'en')
    language = Column(String(10), default='ru')

    # Связь с аккаунтами Telegram, которыми владеет этот пользователь
    accounts = relationship('Account', back_populates='owner')

    def has_permission(self, perm: str) -> bool:
        """
        Check if the user has a specific granular permission.
        superadmin always has all permissions.
        For admin/editor: check the permissions dict; default is True if not set.
        For viewer: no write permissions.
        """
        if self.role == 'superadmin':
            return True
        if self.role == 'viewer':
            # Viewers can only read; deny all configurable write perms
            return False
        # admin / editor: check explicit permissions dict
        if self.permissions and perm in self.permissions:
            return bool(self.permissions[perm])
        return True  # Default: grant permission for admin

    def set_password(self, password: str):
        """Хеширование пароля при создании или смене"""
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def check_password(self, password: str) -> bool:
        """Проверка введенного пароля против хеша в базе"""
        if not self.password_hash:
            return False
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

    def verify_otp(self, token: str) -> bool:
        """Проверка кода двухфакторной аутентификации"""
        if not self.otp_secret:
            return True
        totp = pyotp.TOTP(self.otp_secret)
        return totp.verify(token)

    def is_locked(self) -> bool:
        """
        Проверяет, заблокирован ли вход для пользователя.
        Сравнивает текущее время UTC со временем окончания блокировки.
        """
        if self.locked_until and self.locked_until > datetime.now(timezone.utc):
            return True
        return False

    # ==========================================
    # СВОЙСТВА ДЛЯ ИНТЕГРАЦИИ С FLASK-LOGIN
    # ==========================================
    @property
    def is_authenticated(self):
        """Возвращает True, если пользователь успешно вошел"""
        return True

    @property
    def is_active_status(self):
        """Возвращает текущий статус активности аккаунта"""
        return self.is_active

    @property
    def is_anonymous(self):
        """Возвращает False, так как это реальный пользователь"""
        return False

    def get_id(self):
        """Возвращает уникальный идентификатор пользователя для сессии"""
        return str(self.id)

    def __repr__(self):
        return f"<User {self.username}>"