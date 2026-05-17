# backend/app/services/auth_service.py

"""
AUTH SERVICE LAYER

Handles all authentication business logic.
Routes call these functions — never put this logic in routes.

Authentication lifecycle:
  Register → hash password → save user → return user
  Login → find user → verify password → create JWT → return token
  Protected request → decode JWT → fetch user → return user
"""

from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from uuid import uuid4
from typing import Optional
import logging

from app.models.user import User, UserRole
from app.schemas.auth_schema import UserRegisterSchema, UserLoginSchema
from app.core.security import hash_password, verify_password, create_access_token

logger = logging.getLogger(__name__)


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """
    Fetches a user by email address.
    Used during login and duplicate-check during registration.
    Returns None if not found — never raises an exception.
    """
    return db.query(User).filter(User.email == email.lower()).first()


def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    """
    Fetches a user by UUID.
    Used by get_current_user dependency to load user from JWT token.
    """
    return db.query(User).filter(User.id == user_id).first()


def register_user(db: Session, data: UserRegisterSchema) -> User:
    """
    Creates a new user account.

    Steps:
    1. Check if email already exists
    2. Hash the plain password (NEVER store plain text)
    3. Create User ORM object
    4. Save to database
    5. Return the created user (without password)

    Why check duplicates? Email is the login identifier.
    Two accounts with same email = login ambiguity = security risk.
    """
    # Step 1: Duplicate email check
    existing = get_user_by_email(db, data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists"
        )

    # Step 2: Hash password BEFORE creating the object
    # The plain password should NEVER touch the database layer
    password_hash = hash_password(data.password)
    logger.info(f"Registering new user: {data.email}")

    # Step 3: Build user object
    user = User(
        id=uuid4(),
        email=data.email.lower(),
        hashed_password=password_hash,      # ← hashed, not plain
        full_name=data.full_name,
        phone=data.phone,
        role=UserRole.OWNER,                # New registrations are always OWNER
        business_name=data.business_name,
        gstin=data.gstin,
        pan=data.pan,
        is_active=True,
        is_verified=False,                  # Email verification in future phase
    )

    db.add(user)
    try:
        db.commit()
        db.refresh(user)
        logger.info(f"User registered successfully: {user.id}")
        return user
    except Exception as e:
        db.rollback()
        logger.error(f"Registration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed. Please try again."
        )


def authenticate_user(db: Session, data: UserLoginSchema) -> User:
    """
    Validates login credentials and returns the user.

    Security design:
    - Always say "invalid credentials" for BOTH wrong email AND wrong password.
    - Never say "email not found" — that reveals which emails are registered.
    - This prevents user enumeration attacks.

    Steps:
    1. Look up user by email
    2. Verify password against stored hash
    3. Check account is active
    4. Return authenticated user
    """
    # Step 1: Find user (deliberately vague error message)
    user = get_user_by_email(db, data.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Step 2: Verify password
    if not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",   # Same message — intentional
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Step 3: Check account status
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Please contact support."
        )

    return user


def create_user_token(user: User) -> str:
    """
    Generates a JWT access token for an authenticated user.
    The token embeds the user's UUID as the 'subject'.
    """
    return create_access_token(subject=str(user.id))