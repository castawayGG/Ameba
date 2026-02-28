from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.sql import func
from core.database import Base

class Webhook(Base):
    """Outgoing webhook configuration."""
    __tablename__ = 'webhooks'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    url = Column(String(500), nullable=False)
    secret = Column(String(100), nullable=True)
    events = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    retry_count = Column(Integer, default=3)
    last_triggered = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<Webhook {self.name}>"

class WebhookDelivery(Base):
    """Log of webhook delivery attempts."""
    __tablename__ = 'webhook_deliveries'

    id = Column(Integer, primary_key=True)
    webhook_id = Column(Integer, ForeignKey('webhooks.id', ondelete='CASCADE'), nullable=False)
    event_type = Column(String(50), nullable=False)
    payload = Column(JSON, nullable=True)
    response_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    success = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<WebhookDelivery {self.event_type} {'OK' if self.success else 'FAIL'}>"
