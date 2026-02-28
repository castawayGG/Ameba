from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from core.database import Base


class Notification(Base):
    __tablename__ = 'notifications'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(20), default='info')      # info, warning, error, success
    category = Column(String(50), nullable=True)   # account_ban, flood_wait, proxy_fail, campaign_complete, security
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    related_url = Column(String(500), nullable=True)

    def __repr__(self):
        return f"<Notification {self.id} {self.type} {self.title}>"
