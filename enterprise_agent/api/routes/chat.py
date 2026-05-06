import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from enterprise_agent.api.middleware.auth import get_current_user
from enterprise_agent.api.schemas.chat import ChatRequest, ChatResponse, SessionCreate, SessionResponse
from enterprise_agent.core.agent.graph import get_agent_graph
from enterprise_agent.core.agent.tools.workspace import set_current_user_id
from enterprise_agent.db.mysql import get_db
from enterprise_agent.models.session import Session, SessionStatus

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

    # Set user context for workspace isolation
    set_current_user_id(user_id)

    # Execute agent graph with thread_id for state persistence
    result = await get_agent_graph().ainvoke(
        {
            "session_id": session_id,
            "user_id": user_id,
            "messages": [{"role": "user", "content": request.content}]
        },
        config={"configurable": {"thread_id": session_id}}
    )

    # Get last message (guard against empty messages)
    messages = result.get("messages", [])
    if not messages:
        raise HTTPException(status_code=500, detail="Agent returned no response")
    last_msg = messages[-1]

    # Extract content - handle both string and content block formats
    if hasattr(last_msg, "content"):
        raw_content = last_msg.content

        # Debug logging
        import logging
        logging.debug(f"Content type: {type(raw_content)}, content: {raw_content}")

        # If content is a list of blocks (Anthropic format), extract text
        if isinstance(raw_content, list):
            text_parts = []
            for block in raw_content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                elif hasattr(block, "text"):
                    text_parts.append(block.text)
            content = "\n".join(text_parts) if text_parts else str(raw_content)
        elif isinstance(raw_content, str):
            # Try to parse if it looks like a list representation
            if raw_content.startswith("[") and raw_content.endswith("]"):
                try:
                    import ast
                    parsed = ast.literal_eval(raw_content)
                    if isinstance(parsed, list):
                        text_parts = []
                        for block in parsed:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                        content = "\n".join(text_parts) if text_parts else raw_content
                    else:
                        content = raw_content
                except:
                    content = raw_content
            else:
                content = raw_content
        else:
            content = str(raw_content)
    else:
        content = str(last_msg)

    return ChatResponse(
        session_id=session_id,
        role="assistant",
        content=content,
        created_at=datetime.now(timezone.utc)
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

    # Set user context for workspace isolation
    set_current_user_id(user_id)

    async def generate():
        # Stream agent execution with thread_id for state persistence
        async for event in get_agent_graph().astream_events(
            {
                "session_id": session_id,
                "user_id": user_id,
                "messages": [{"role": "user", "content": request.content}]
            },
            config={"configurable": {"thread_id": session_id}},
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
            created_at=s.created_at
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