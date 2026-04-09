from sqlalchemy import Column, Float, ForeignKey, Integer

from app.core.database import Base


class UserBalance(Base):
    __tablename__ = "user_balances"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    monthly_amount = Column(Float, default=10.0)

