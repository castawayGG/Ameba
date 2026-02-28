from sqlalchemy import Column, Integer, String, Table, ForeignKey
from core.database import Base


account_tags = Table(
    'account_tags',
    Base.metadata,
    Column('account_id', String(32), ForeignKey('accounts.id')),
    Column('tag_id', Integer, ForeignKey('tags.id'))
)


class Tag(Base):
    __tablename__ = 'tags'

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    color = Column(String(7), default='#6B7280')

    def __repr__(self):
        return f"<Tag {self.name}>"
