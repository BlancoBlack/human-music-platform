from sqlalchemy import Column, Float, Integer

from app.core.database import Base


class GlobalListeningAggregate(Base):
    __tablename__ = "global_listening_aggregates"

    id = Column(Integer, primary_key=True, index=True)

    song_id = Column(Integer)
    total_duration = Column(Float)

