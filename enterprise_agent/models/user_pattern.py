from sqlalchemy import Column, BigInteger, String, JSON, TIMESTAMP, ForeignKey, Numeric, Integer
from sqlalchemy.orm import relationship
from datetime import datetime

from enterprise_agent.db.mysql import Base


class UserPreference(Base):
    """User preference model for storing user settings"""
    __tablename__ = "user_preferences"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    preference_key = Column(String(100), nullable=False)
    preference_value = Column(JSON, nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="preferences")


class UserPattern(Base):
    """User pattern model for learning user behaviors"""
    __tablename__ = "user_patterns"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    pattern_type = Column(String(50), nullable=False)  # 'preference', 'workflow', 'shortcut'
    pattern_key = Column(String(100), nullable=False)
    pattern_value = Column(JSON, nullable=False)
    confidence_score = Column(Numeric(5, 4), default=1.0)
    usage_count = Column(Integer, default=1)
    last_used_at = Column(TIMESTAMP, default=datetime.utcnow)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="patterns")