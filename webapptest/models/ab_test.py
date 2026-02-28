from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Float
from sqlalchemy.sql import func
from core.database import Base

class ABTest(Base):
    __tablename__ = 'ab_tests'
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    description = Column(String(500))
    status = Column(String(20), default='draft')  # draft, running, completed, paused
    variants = Column(JSON)  # [{"name": "A", "landing_id": 1, "weight": 50}, ...]
    total_visits = Column(Integer, default=0)
    winner_variant = Column(String(50))
    created_by = Column(Integer, ForeignKey('users.id'))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())

class ABTestVisit(Base):
    __tablename__ = 'ab_test_visits'
    id = Column(Integer, primary_key=True)
    test_id = Column(Integer, ForeignKey('ab_tests.id', ondelete='CASCADE'), nullable=False)
    variant_name = Column(String(50), nullable=False)
    ip = Column(String(45))
    converted = Column(Boolean, default=False)
    visited_at = Column(DateTime, server_default=func.now())
