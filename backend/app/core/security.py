# backend/app/core/security.py

"""
SECURITY LAYER — Cryptographic operations only.

Two responsibilities:
1. Password hashing (bcrypt) — never store plain passwords
2. JWT tokens — prove identity on every request

Nothing else belongs here. No database calls, no business logic.
"""

from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ─────────────────────────────────────────────
# PASSWORD HASHING
# ─────────────────────────────────────────────

# CryptContext manages hashing algorithms.
# bcrypt is the industry standard for passwords because:
# 1. It's intentionally slow (prevents brute force)
# 2. It auto-generates a unique salt per password
# 3. The hash includes the salt, so you never store salt separately
# deprecated="auto" means old hashes get auto-upgraded to bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """
    Converts plain text password to a bcrypt hash.

    Example:
        "mysecret123" → "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"

    The hash is different every time even for the same password
    because bcrypt auto-generates a random salt.
    NEVER store the plain password. Store only this hash.
    """
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Checks if a plain password matches a stored hash.

    This is safe because:
    - bcrypt extracts the salt from the stored hash
    - rehashes the plain password with that salt
    - compares the result

    Returns True if match, False otherwise.
    Never raises an exception — always returns a boolean.
    """
    return pwd_context.verify(plain_password, hashed_password)


# ─────────────────────────────────────────────
# JWT TOKEN OPERATIONS
# ─────────────────────────────────────────────

"""
How JWT works:
─────────────
1. User logs in with email + password
2. Server verifies credentials
3. Server creates a JWT token containing user's ID
4. Token is signed with SECRET_KEY → tamper-proof
5. Client stores token and sends it with every request
6. Server decodes token → knows who is making the request

Token structure (3 parts separated by dots):
  header.payload.signature
  eyJhbG...  eyJ1c2...  SflKxwR...

The payload contains: user_id, expiry time
The signature proves nobody modified the payload
"""


def create_access_token(
    subject: str,               # Usually the user's UUID as string
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Creates a signed JWT token.

    Args:
        subject: The user ID to embed in the token
        expires_delta: How long until token expires

    Returns:
        JWT token string to send to client
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    # Payload = data embedded in the token
    # 'sub' (subject) is the standard JWT claim for user identity
    # 'exp' (expiry) tells the server when to reject this token
    payload = {
        "sub": subject,         # user UUID as string
        "exp": expire,          # expiry datetime
        "iat": datetime.utcnow() # issued at (when token was created)
    }

    # Sign the token with our SECRET_KEY
    # Anyone can READ a JWT (it's base64 encoded, not encrypted)
    # But nobody can MODIFY it without knowing the SECRET_KEY
    token = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    return token


def decode_access_token(token: str) -> Optional[str]:
    """
    Decodes and validates a JWT token.

    Returns the user_id (subject) if token is valid.
    Returns None if token is expired, tampered, or invalid.

    This never raises exceptions — the route handles error responses.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        return user_id
    except JWTError:
        # Covers: expired tokens, invalid signature, malformed tokens
        return None