# backend/app/api/auth/routes.py

"""
AUTH ROUTES — Registration, Login, Profile

These routes are intentionally thin.
All logic lives in auth_service.py.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.auth_schema import (
    UserRegisterSchema,
    UserLoginSchema,
    TokenSchema,
    UserResponseSchema,
)
from app.services.auth_service import (
    register_user,
    authenticate_user,
    create_user_token,
)
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account"
)
def register(data: UserRegisterSchema, db: Session = Depends(get_db)):
    """
    Creates a new user account.
    Password is hashed before storage — plain password never saved.
    """
    user = register_user(db, data)
    return user


@router.post(
    "/login",
    response_model=TokenSchema,
    summary="Login and get JWT access token"
)
def login(data: UserLoginSchema, db: Session = Depends(get_db)):
    """
    Authenticates user and returns a JWT token.

    The client must store this token and send it as:
        Authorization: Bearer <token>
    on every subsequent request to protected endpoints.
    """
    user = authenticate_user(db, data)
    token = create_user_token(user)
    return TokenSchema(access_token=token)


@router.get(
    "/me",
    response_model=UserResponseSchema,
    summary="Get current logged-in user profile"
)
def get_me(current_user: User = Depends(get_current_user)):
    """
    Returns the profile of the currently logged-in user.
    Requires a valid JWT token in the Authorization header.

    This route is also useful for verifying your token is working.
    """
    return current_user