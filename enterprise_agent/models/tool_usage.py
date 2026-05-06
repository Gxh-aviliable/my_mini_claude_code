from datetime import datetime, timezone

from sqlalchemy import JSON, TIMESTAMP, BigInteger, Boolean, Column, ForeignKey, Integer, String, Text

from enterprise_agent.db.mysql import Base


class ToolUsageLog(Base):
    """Tool usage log model for analytics"""
    __tablename__ = "tool_usage_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    tool_name = Column(String(50), nullable=False)
    tool_input = Column(JSON, nullable=True)
    tool_result_summary = Column(String(500), nullable=True)
    execution_time_ms = Column(Integer, nullable=True)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc), index=True)