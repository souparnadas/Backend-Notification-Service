from sqlalchemy import Column, String, Integer, Boolean, Enum, JSON, DateTime, create_engine
from sqlalchemy.orm import declarative_base
from datetime import datetime
import enum
import os

Base = declarative_base()

class ChannelType(str, enum.Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    PUSH = "PUSH"

class NotificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"

class PriorityLevel(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"

class UserPreference(Base):
    __tablename__ = "user_preferences"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    channel = Column(Enum(ChannelType), nullable=False)
    is_enabled = Column(Boolean, default=True)

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    channel = Column(Enum(ChannelType), nullable=False)
    priority = Column(Enum(PriorityLevel), default=PriorityLevel.NORMAL)
    status = Column(Enum(NotificationStatus), default=NotificationStatus.PENDING)
    payload = Column(JSON, nullable=False)
    idempotency_key = Column(String, unique=True, index=True, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class Webhook(Base):
    __tablename__ = "webhooks"
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, nullable=False)
# Database connection specifically for Docker
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:password@db:5432/notification_db")
engine = create_engine(DATABASE_URL)
Base.metadata.create_all(bind=engine)