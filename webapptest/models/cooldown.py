from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from core.database import Base

class CooldownRule(Base):
    __tablename__ = 'cooldown_rules'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    action_type = Column(String(50))
    min_delay = Column(Integer, default=30)
    max_delay = Column(Integer, default=120)
    max_per_hour = Column(Integer, default=20)
    max_per_day = Column(Integer, default=100)
    burst_limit = Column(Integer, default=5)
    burst_cooldown = Column(Integer, default=300)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

class CooldownLog(Base):
    __tablename__ = 'cooldown_logs'
    id = Column(Integer, primary_key=True)
    account_id = Column(String(64), ForeignKey('accounts.id'))
    action_type = Column(String(50))
    performed_at = Column(DateTime, server_default=func.now())
    delay_applied = Column(Integer)
    was_throttled = Column(Boolean, default=False)
