from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.sql import func
from core.database import Base

class AccountPool(Base):
    """Pool of accounts for rotation and campaign targeting."""
    __tablename__ = 'account_pools'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    selection_strategy = Column(String(20), default='round_robin')  # round_robin, random, least_used
    max_actions_per_account = Column(Integer, default=50)
    cooldown_minutes = Column(Integer, default=60)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<AccountPool {self.name}>"

class AccountPoolMember(Base):
    """Association between accounts and pools."""
    __tablename__ = 'account_pool_members'

    id = Column(Integer, primary_key=True)
    pool_id = Column(Integer, ForeignKey('account_pools.id', ondelete='CASCADE'), nullable=False)
    account_id = Column(String(32), ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False)
    added_at = Column(DateTime, server_default=func.now())
