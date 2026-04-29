from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from enterprise_agent.db.mysql import get_db
from enterprise_agent.models.user import User
from enterprise_agent.auth.jwt_handler import jwt_handler
from enterprise_agent.auth.permissions import get_role_permissions
from enterprise_agent.api.schemas.auth import UserRegister, UserLogin, TokenResponse, TokenRefresh

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
async def register(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db)
):
    """Register new user

    Args:
        user_data: Registration data
        db: Database session

    Returns:
        JWT tokens

    Raises:
        HTTPException: If username or email already exists
    """
    # Check if username exists
    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already registered")

    # Check if email exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create user
    user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=jwt_handler.hash_password(user_data.password),
        full_name=user_data.full_name
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Return tokens with free role permissions
    permissions = [p.value for p in get_role_permissions("free")]
    return jwt_handler.create_tokens(user.id, permissions)


@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """Login user

    Args:
        login_data: Login credentials
        db: Database session

    Returns:
        JWT tokens

    Raises:
        HTTPException: If credentials are invalid
    """
    result = await db.execute(select(User).where(User.username == login_data.username))
    user = result.scalar_one_or_none()

    if not user or not jwt_handler.verify_password(login_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is disabled")

    # Update last login time
    user.last_login_at = datetime.utcnow()
    await db.commit()

    # Get role permissions (simplified: admin if superuser, else pro)
    role = "admin" if user.is_superuser else "pro"
    permissions = [p.value for p in get_role_permissions(role)]

    return jwt_handler.create_tokens(user.id, permissions)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_data: TokenRefresh,
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token

    Args:
        refresh_data: Refresh token
        db: Database session

    Returns:
        New JWT tokens

    Raises:
        HTTPException: If refresh token is invalid
    """
    payload = jwt_handler.verify_token(refresh_data.refresh_token, "refresh")
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    result = await db.execute(select(User).where(User.id == payload.sub))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or disabled")

    role = "admin" if user.is_superuser else "pro"
    permissions = [p.value for p in get_role_permissions(role)]

    return jwt_handler.create_tokens(user.id, permissions)