from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class Artist(Base):
    __tablename__ = "artists"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    system_key = Column(String(64), unique=True, nullable=True)
    payout_method = Column(String(32), nullable=False, default="none")
    payout_wallet_address = Column(String(255), nullable=True)
    payout_bank_info = Column(String(255), nullable=True)
    is_system = Column(Boolean, default=False, nullable=False)

    user = relationship(
        "User",
        back_populates="linked_artists",
        foreign_keys=[user_id],
    )
