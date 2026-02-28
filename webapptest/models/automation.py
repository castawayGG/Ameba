from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from core.database import Base


class Automation(Base):
    __tablename__ = 'automations'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    trigger_type = Column(String(50), nullable=False)
    trigger_config = Column(JSON, nullable=True)
    steps = Column(JSON, nullable=False, default=lambda: [])
    is_active = Column(Boolean, default=True)
    runs_count = Column(Integer, default=0)
    last_run = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
