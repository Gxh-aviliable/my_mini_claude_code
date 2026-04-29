from sqlalchemy import Column, String, BigInteger, JSON, TIMESTAMP, Enum, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from enterprise_agent.db.mysql import Base


class SessionStatus(str, enum.Enum):
    """Session status enum"""
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class Session(Base):
    """Session model for conversation sessions"""
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=True)
    status = Column(Enum(SessionStatus), default=SessionStatus.ACTIVE)
    metadata = Column(JSON, default={})
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="sessions")
    messages = relationship("ConversationMessage", back_populates="session", cascade="all, delete-orphan")