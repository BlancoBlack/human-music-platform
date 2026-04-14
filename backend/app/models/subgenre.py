from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class Subgenre(Base):
    __tablename__ = "subgenres"
    __table_args__ = (
        UniqueConstraint("genre_id", "name", name="uq_subgenres_genre_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    genre_id = Column(Integer, ForeignKey("genres.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    slug = Column(String(128), nullable=False, unique=True, index=True)

    genre = relationship("Genre")
