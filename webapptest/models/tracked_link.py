from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from core.database import Base


class TrackedLink(Base):
    __tablename__ = 'tracked_links'

    id = Column(Integer, primary_key=True)
    short_code = Column(String(20), unique=True, nullable=False, index=True)
    destination_url = Column(String(2000), nullable=False)
    campaign_id = Column(Integer, ForeignKey('campaigns.id'), nullable=True)
    clicks = Column(Integer, default=0)
    unique_clicks = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class LinkClick(Base):
    __tablename__ = 'link_clicks'

    id = Column(Integer, primary_key=True)
    link_id = Column(Integer, ForeignKey('tracked_links.id', ondelete='CASCADE'), nullable=False)
    ip = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    country = Column(String(50), nullable=True)
    device_type = Column(String(20), nullable=True)
    os = Column(String(50), nullable=True)
    browser = Column(String(50), nullable=True)
    referer = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
