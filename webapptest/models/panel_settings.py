from sqlalchemy import Column, Integer, String, Text
from core.database import Base

class PanelSettings(Base):
    """Key-value store for panel customization settings."""
    __tablename__ = 'panel_settings'

    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)

    def __repr__(self):
        return f"<PanelSettings {self.key}>"
