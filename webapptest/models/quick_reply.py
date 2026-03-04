from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from core.database import Base


class QuickReply(Base):
    """Pre-written quick reply templates for fast response in the inbox."""
    __tablename__ = 'quick_replies'

    id = Column(Integer, primary_key=True)
    title = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(50), default='general')
    shortcut = Column(String(30), nullable=True, unique=True)  # e.g. /hello
    created_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'category': self.category,
            'shortcut': self.shortcut,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
