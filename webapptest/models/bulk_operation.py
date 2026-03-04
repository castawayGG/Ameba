from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Text
from sqlalchemy.sql import func
from core.database import Base


class BulkOperation(Base):
    """History log of bulk operations performed by admins."""
    __tablename__ = 'bulk_operations'

    id = Column(Integer, primary_key=True)
    operation_type = Column(String(100), nullable=False)  # e.g. 'bulk_delete', 'bulk_assign_proxy'
    status = Column(String(20), default='pending')  # pending / running / completed / failed / cancelled
    total = Column(Integer, default=0)
    processed = Column(Integer, default=0)
    succeeded = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    # Per-item error details: [{"id": "...", "error": "..."}, ...]
    errors = Column(JSON, nullable=True, default=list)
    params = Column(JSON, nullable=True)  # Input parameters snapshot
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
