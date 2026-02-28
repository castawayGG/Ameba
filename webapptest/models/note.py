from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from core.database import Base

class Note(Base):
    """Notes attachable to any entity (account, victim, campaign, landing)."""
    __tablename__ = 'notes'

    id = Column(Integer, primary_key=True)
    entity_type = Column(String(30), nullable=False, index=True)  # account, victim, campaign, landing
    entity_id = Column(String(64), nullable=False, index=True)
    content = Column(Text, nullable=False)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Note {self.entity_type}:{self.entity_id}>"
