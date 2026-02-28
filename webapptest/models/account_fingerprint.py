from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from core.database import Base

class AccountFingerprint(Base):
    """Digital identity/fingerprint for a Telegram account."""
    __tablename__ = 'account_fingerprints'

    id = Column(Integer, primary_key=True)
    account_id = Column(String(32), ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    device_model = Column(String(100), nullable=True)
    os_version = Column(String(50), nullable=True)
    app_version = Column(String(50), nullable=True)
    language = Column(String(10), default='en')
    timezone = Column(String(50), default='UTC')
    online_schedule = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<AccountFingerprint account_id={self.account_id}>"
