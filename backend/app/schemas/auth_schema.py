# backend/app/schemas/auth_schema.py

"""
AUTH SCHEMAS

These validate what comes IN and control what goes OUT
for all authentication endpoints.

Security rule: NEVER include hashed_password in any response schema.
Once a password is hashed and stored, it should never leave the server.
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime
from enum import Enum
import re


class UserRoleEnum(str, Enum):
    OWNER = "OWNER"
    ACCOUNTANT = "ACCOUNTANT"
    ADMIN = "ADMIN"


# ─────────────────────────────────────────────
# REGISTRATION
# ─────────────────────────────────────────────

class UserRegisterSchema(BaseModel):
    """What the client sends to create an account."""
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=100)
    full_name: str = Field(..., min_length=2, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    business_name: Optional[str] = Field(None, max_length=200)
    gstin: Optional[str] = Field(None, max_length=15)
    pan: Optional[str] = Field(None, max_length=10)

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        v = v.lower().strip()
        pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        if not re.match(pattern, v):
            raise ValueError("Invalid email format")
        return v

    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        """
        Production password rules:
        - At least 8 characters
        - At least one digit
        - At least one uppercase letter
        """
        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one digit")
        if not any(char.isupper() for char in v):
            raise ValueError("Password must contain at least one uppercase letter")
        return v

    @field_validator('gstin')
    @classmethod
    def validate_gstin(cls, v):
        if v is not None:
            v = v.upper().strip()
            pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'
            if not re.match(pattern, v):
                raise ValueError("Invalid GSTIN format")
        return v


# ─────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────

class UserLoginSchema(BaseModel):
    """What the client sends to log in."""
    email: str = Field(..., max_length=255)
    password: str = Field(..., max_length=100)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, v):
        return v.lower().strip()


# ─────────────────────────────────────────────
# TOKEN RESPONSE
# ─────────────────────────────────────────────

class TokenSchema(BaseModel):
    """
    What the server returns after successful login.
    The client stores this token and sends it with every future request.
    """
    access_token: str
    token_type: str = "bearer"  # Standard OAuth2 token type


# ─────────────────────────────────────────────
# USER RESPONSE
# ─────────────────────────────────────────────

class UserResponseSchema(BaseModel):
    """
    Safe user data for API responses.
    Notice: NO hashed_password field. Never expose this.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    phone: Optional[str]
    role: str
    business_name: Optional[str]
    gstin: Optional[str]
    pan: Optional[str]
    is_active: bool
    is_verified: bool
    created_at: datetime