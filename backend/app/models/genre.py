from sqlalchemy import Column, Integer, String

from app.core.database import Base


class Genre(Base):
    __tablename__ = "genres"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False, unique=True, index=True)
    slug = Column(String(128), nullable=False, unique=True, index=True)
