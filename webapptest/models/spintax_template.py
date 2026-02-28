from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from core.database import Base

class SpintaxTemplate(Base):
    __tablename__ = 'spintax_templates'
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(50))
    language = Column(String(10), default='uk')
    variables = Column(JSON)
    test_count = Column(Integer, default=0)
    created_by = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, server_default=func.now())
