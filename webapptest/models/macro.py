from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.sql import func
from core.database import Base


class Macro(Base):
    """A recorded sequence of bulk actions that can be replayed on a group of accounts."""
    __tablename__ = 'macros'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    # List of step dicts: [{"action": "assign_proxy", "params": {...}}, ...]
    steps = Column(JSON, nullable=False, default=list)
    is_active = Column(Boolean, default=True)
    runs_count = Column(Integer, default=0)
    last_run = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
