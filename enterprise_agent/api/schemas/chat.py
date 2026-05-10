from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Chat request"""
    session_id: Optional[str] = None
    content: str = Field(..., min_length=1, max_length=10000)
    stream: bool = True


class ChatResponse(BaseModel):
    """Chat response"""
    session_id: str
    message_id: Optional[int] = None
    role: str
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    created_at: datetime


class SessionCreate(BaseModel):
    """Session creation request"""
    title: Optional[str] = Field(None, max_length=255)


class SessionResponse(BaseModel):
    """Session response"""
    id: str
    user_id: int
    title: Optional[str]
    status: str
    created_at: datetime
    message_count: Optional[int] = 0


class ResumeRequest(BaseModel):
    """Resume request after tool confirmation"""
    approved_ids: List[str] = Field(default_factory=list)