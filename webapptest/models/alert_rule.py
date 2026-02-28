from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from core.database import Base

class AlertRule(Base):
    __tablename__ = 'alert_rules'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    event_type = Column(String(50), nullable=False)
    condition = Column(JSON, nullable=True)
    action = Column(String(50), nullable=False)
    action_params = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
