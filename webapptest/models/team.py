from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.sql import func
from core.database import Base

class Comment(Base):
    __tablename__ = 'comments'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(50), nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

class TeamTask(Base):
    __tablename__ = 'team_tasks'
    id = Column(Integer, primary_key=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    assigned_to = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    status = Column(String(20), default='todo')
    priority = Column(String(20), default='medium')
    due_date = Column(DateTime, nullable=True)
    related_entity_type = Column(String(50), nullable=True)
    related_entity_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

class Announcement(Base):
    __tablename__ = 'announcements'
    id = Column(Integer, primary_key=True)
    title = Column(String(300), nullable=False)
    text = Column(Text, nullable=False)
    author_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    priority = Column(String(20), default='normal')
    is_pinned = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class SharedTemplate(Base):
    __tablename__ = 'shared_templates'
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    type = Column(String(30), nullable=False)
    content = Column(JSON, nullable=False)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    is_shared = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

class UserQuota(Base):
    __tablename__ = 'user_quotas'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)
    max_accounts = Column(Integer, default=100)
    max_campaigns_per_day = Column(Integer, default=10)
    max_messages_per_day = Column(Integer, default=500)
    max_proxy_slots = Column(Integer, default=50)
