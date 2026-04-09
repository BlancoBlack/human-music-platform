from sqlalchemy import Column, Float, ForeignKey, Integer

from app.core.database import Base


class ListeningAggregate(Base):
    __tablename__ = "listening_aggregates"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    song_id = Column(Integer, ForeignKey("songs.id"))
    total_duration = Column(Float, default=0.0)
    weighted_duration = Column(Float, default=0.0)

