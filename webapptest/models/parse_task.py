from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from core.database import Base

class ParseTask(Base):
    __tablename__ = 'parse_tasks'
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    source_type = Column(String(30))
    source_link = Column(String(500))
    account_id = Column(String(64), ForeignKey('accounts.id'))
    status = Column(String(30), default='pending')
    total_parsed = Column(Integer, default=0)
    filters = Column(JSON)
    result_data = Column(JSON)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_by = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, server_default=func.now())
