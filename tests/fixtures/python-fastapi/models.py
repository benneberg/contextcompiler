"""Database models."""
from sqlalchemy import Column, Integer, String, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class UserModel(Base):
    """User database model."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    platform = Column(SQLEnum("android", "ios", "web", name="platform_type"))
