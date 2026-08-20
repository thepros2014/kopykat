"""
auth.py — User registration, login, JWT sessions, API key management.
"""

import os
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordBearer
import bcrypt
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .database import get_db, User, APIKey

# ── Config ────────────────────────────────────────────────────────────────────

SECRET_KEY    = os.getenv("JWT_SECRET_KEY", secrets.token_hex(32))
ALGORITHM     = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours (was 7 days)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash password using bcrypt directly (avoids passlib wrap bug with bcrypt >= 4)."""
    pwd_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify password against bcrypt hash."""
    try:
        pwd_bytes = plain.encode("utf-8")[:72]
        hashed_bytes = hashed.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hashed_bytes)
    except Exception:
        return False


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# ── API Key helpers ───────────────────────────────────────────────────────────

def generate_api_key() -> tuple[str, str, str]:
    """
    Returns (raw_key, key_hash, key_prefix).
    raw_key is shown to user ONCE — only the hash is stored.
    """
    raw_key    = "sc_" + secrets.token_urlsafe(40)
    key_hash   = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:11]
    return raw_key, key_hash, key_prefix


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


# ── FastAPI dependencies ──────────────────────────────────────────────────────

def get_current_user_jwt(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Dependency: validates JWT token and returns the User."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    payload = decode_access_token(token)
    if not payload:
        raise credentials_exception
    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or not user.is_active:
        raise credentials_exception
    return user


def get_current_user_apikey(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    db: Session = Depends(get_db),
) -> tuple[User, APIKey]:
    """
    Dependency: validates an API key from Authorization: Bearer sc_... header.
    Returns (User, APIKey) tuple.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="API key required")

    raw_key  = credentials.credentials
    key_hash = hash_api_key(raw_key)

    api_key = db.query(APIKey).filter(
        APIKey.key_hash == key_hash,
        APIKey.is_active == True,
    ).first()

    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")

    user = db.query(User).filter(User.id == api_key.user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="Account not found or suspended")

    # Update last-used timestamp
    api_key.last_used = datetime.utcnow()
    api_key.requests_today += 1
    db.commit()

    return user, api_key


# ── Business logic ────────────────────────────────────────────────────────────

def register_user(email: str, password: str, full_name: Optional[str], db: Session) -> User:
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        id=str(uuid.uuid4()),
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        plan="free",
        credits=5000,
        monthly_limit=5000,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(email: str, password: str, db: Session) -> Optional[User]:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_user_api_key(user: User, name: str, db: Session) -> tuple[str, APIKey]:
    """Creates and stores a new API key for a user. Returns (raw_key, APIKey)."""
    # Enforce max 5 keys per user
    existing_count = db.query(APIKey).filter(
        APIKey.user_id == user.id, APIKey.is_active == True
    ).count()
    if existing_count >= 5:
        raise HTTPException(status_code=400, detail="Maximum 5 API keys per account")

    raw_key, key_hash, key_prefix = generate_api_key()

    api_key = APIKey(
        id=str(uuid.uuid4()),
        user_id=user.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=name,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    return raw_key, api_key


def revoke_api_key(key_id: str, user: User, db: Session) -> bool:
    api_key = db.query(APIKey).filter(
        APIKey.id == key_id,
        APIKey.user_id == user.id,
    ).first()
    if not api_key:
        return False
    api_key.is_active = False
    db.commit()
    return True
