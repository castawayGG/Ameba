from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from core.database import Base


class LandingPage(Base):
    __tablename__ = 'landing_pages'

    id = Column(Integer, primary_key=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    html_content = Column(Text, nullable=False)
    css_content = Column(Text, nullable=True)
    js_content = Column(Text, nullable=True)
    language = Column(String(10), default='uk')
    theme = Column(String(30), default='telegram')
    is_active = Column(Boolean, default=True)
    visits = Column(Integer, default=0)
    conversions = Column(Integer, default=0)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
