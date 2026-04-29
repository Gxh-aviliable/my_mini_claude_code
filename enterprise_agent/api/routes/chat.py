from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
import uuid
import json

from enterprise_agent.api.middleware.auth import get_current_user
from enterprise_agent.api.schemas.chat import ChatRequest, ChatResponse, SessionCreate, SessionResponse
from enterprise_agent.db.mysql import get_db
from enterprise_agent.db.redis import redis_client
from enterprise_agent.memory.short_term import ShortTermMemory
from enterprise_agent.models.session import Session, SessionStatus
from enterprise_agent.core.agent.graph import agent_graph

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/completions", response_model=ChatResponse)
async def chat_completion(
    request: ChatRequest,
    user_id: int = Depends(get_current_user)
):
    """Non-streaming chat completion

    Args:
        request: Chat request
        user_id: Current user ID from JWT

    Returns:
        Chat response
    """
    session_id = request.session_id or str(uuid.uuid4())

    stm = ShortTermMemory(redis_client)

    # Add user message to Redis
    await stm.append_message(session_id, "user", request.content)

    # Execute agent graph
    result = await agent_graph.ainvoke({
        "session_id": session_id,
        "user_id": user_id,
        "messages": [{"role": "user", "content": request.content}]
    })

    # Get last message
    last_msg = result.get("messages", [])[-1]
    content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    return ChatResponse(
        session_id=session_id,
        message_id=0,
        role="assistant",
        content=content,
        created_at=datetime.utcnow()
    )


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    user_id: int = Depends(get_current_user)
):
    """Streaming chat completion (SSE)

    Args:
        request: Chat request
        user_id: Current user ID from JWT

    Returns:
        StreamingResponse with SSE events
    """
    session_id = request.session_id or str(uuid.uuid4())

    async def generate():
        stm = ShortTermMemory(redis_client)
        await stm.append_message(session_id, "user", request.content)

        # Stream agent execution
        async for event in agent_graph.astream_events(
            {
                "session_id": session_id,
                "user_id": user_id,
                "messages": [{"role": "user", "content": request.content}]
            },
            version="v1"
        ):
            if event.get("event") == "on_chain_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk:
                    delta = chunk.content if hasattr(chunk, "content") else str(chunk)
                    yield f"data: {json.dumps({'delta': delta})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# Session management routes
sessions_router = APIRouter(prefix="/sessions", tags=["sessions"])


@sessions_router.get("/", response_model=list[SessionResponse])
async def list_sessions(
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List user sessions

    Args:
        user_id: Current user ID
        db: Database session

    Returns:
        List of sessions
    """
    result = await db.execute(
        select(Session).where(
            Session.user_id == user_id,
            Session.status != SessionStatus.DELETED
        )
    )
    sessions = result.scalars().all()

    return [
        SessionResponse(
            id=s.id,
            user_id=s.user_id,
            title=s.title,
            status=s.status.value,
            created_at=s.created_at,
            message_count=0
        )
        for s in sessions
    ]


@sessions_router.post("/", response_model=SessionResponse)
async def create_session(
    data: SessionCreate,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create new session

    Args:
        data: Session creation data
        user_id: Current user ID
        db: Database session

    Returns:
        New session
    """
    session = Session(
        id=str(uuid.uuid4()),
        user_id=user_id,
        title=data.title,
        status=SessionStatus.ACTIVE
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        title=session.title,
        status=session.status.value,
        created_at=session.created_at,
        message_count=0
    )


@sessions_router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete session (soft delete)

    Args:
        session_id: Session ID
        user_id: Current user ID
        db: Database session

    Returns:
        Success message

    Raises:
        HTTPException: If session not found
    """
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == user_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.status = SessionStatus.DELETED
    await db.commit()

    return {"message": "Session deleted"}