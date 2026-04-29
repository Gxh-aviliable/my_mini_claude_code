from sqlalchemy import Column, BigInteger, String, Text, JSON, TIMESTAMP, Enum, ForeignKey, Integer
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from enterprise_agent.db.mysql import Base


class MessageRole(str, enum.Enum):
    """Message role enum"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ConversationMessage(Base):
    """Conversation message model for storing chat history"""
    __tablename__ = "conversation_messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(MessageRole), nullable=False)
    content = Column(Text, nullable=True)
    tool_name = Column(String(50), nullable=True)
    tool_input = Column(JSON, nullable=True)
    tool_result = Column(Text, nullable=True)
    token_count = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, index=True)

    # Relationships
    session = relationship("Session", back_populates="messages")