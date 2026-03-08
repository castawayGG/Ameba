from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from core.database import Base


class WarmingScenario(Base):
    __tablename__ = 'warming_scenarios'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    actions = Column(JSON, nullable=True)          # list of actions
    interval_minutes = Column(Integer, default=30)
    duration_hours = Column(Integer, default=24)
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<WarmingScenario {self.name}>"


class WarmingSession(Base):
    __tablename__ = 'warming_sessions'

    id = Column(Integer, primary_key=True)
    account_id = Column(String(32), ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False)
    scenario_id = Column(Integer, ForeignKey('warming_scenarios.id'), nullable=False)
    status = Column(String(20), default='pending')  # pending, running, completed, failed
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    progress = Column(JSON, nullable=True)

    def __repr__(self):
        return f"<WarmingSession {self.id} {self.status}>"
