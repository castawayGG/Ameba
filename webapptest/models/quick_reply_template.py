from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from core.database import Base


class QuickReplyTemplate(Base):
    """Quick reply (snippet) templates for fast responses in the inbox.

    Maps to the quick_reply_templates table.
    Field names follow the canonical spec: title, text, author_id, created_at.
    """
    __tablename__ = 'quick_reply_templates'

    id = Column(Integer, primary_key=True)
    title = Column(String(100), nullable=False)
    text = Column(Text, nullable=False)
    category = Column(String(50), default='general')
    shortcut = Column(String(30), nullable=True, unique=True)
    author_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'text': self.text,
            'category': self.category,
            'shortcut': self.shortcut,
            'author_id': self.author_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
