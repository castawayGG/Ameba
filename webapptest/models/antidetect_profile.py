from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base

class AntidetectProfile(Base):
    __tablename__ = 'antidetect_profiles'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    device_model = Column(String(100))
    system_version = Column(String(50))
    app_version = Column(String(50))
    lang_code = Column(String(10), default='uk')
    system_lang_code = Column(String(10), default='uk')
    sdk_version = Column(Integer, default=34)
    device_hash = Column(String(64))
    account_id = Column(String(64), ForeignKey('accounts.id'), nullable=True)
    is_template = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
