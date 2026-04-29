from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from enterprise_agent.auth.jwt_handler import jwt_handler


security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> int:
    """Get current user ID from JWT token

    Args:
        credentials: HTTP Bearer credentials

    Returns:
        User ID

    Raises:
        HTTPException: If token is invalid
    """
    payload = jwt_handler.verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload.sub


async def get_current_user_permissions(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> list:
    """Get current user permissions from JWT token

    Args:
        credentials: HTTP Bearer credentials

    Returns:
        List of permission strings

    Raises:
        HTTPException: If token is invalid
    """
    payload = jwt_handler.verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload.permissions or []


def require_permission(required_permission: str):
    """Dependency factory for permission checking

    Args:
        required_permission: Required permission string

    Returns:
        Dependency function
    """
    async def check_permission(
        permissions: list = Depends(get_current_user_permissions)
    ):
        if required_permission not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{required_permission}' required"
            )
        return True
    return check_permission