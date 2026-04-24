from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True, index=True)

    permissions = relationship(
        "Permission",
        secondary="role_permissions",
        back_populates="roles",
    )
    users = relationship(
        "User",
        secondary="user_roles",
        primaryjoin="Role.name == foreign(UserRole.role)",
        secondaryjoin="foreign(UserRole.user_id) == User.id",
        viewonly=True,
    )
