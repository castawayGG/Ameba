import secrets
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from core.database import Base

class ApiKey(Base):
    """API key for external access to the admin API."""
    __tablename__ = 'api_keys'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    key = Column(String(64), unique=True, nullable=False, index=True)
    permissions = Column(JSON, default=list)
    rate_limit = Column(Integer, default=100)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    last_used = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    @staticmethod
    def generate_key():
        """Generate a secure random API key."""
        return secrets.token_urlsafe(48)

    def __repr__(self):
        return f"<ApiKey {self.name}>"
