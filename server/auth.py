"""
auth.py — User registration, login, JWT sessions, API key management.
"""

import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordBearer
import bcrypt
import jwt
from jwt.exceptions import PyJWTError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet

from .database import get_db, User, APIKey
from .config import INTEGRATION_ENCRYPTION_KEY, JWT_SECRET_KEY, env_int

#  Config 

SECRET_KEY = JWT_SECRET_KEY

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = env_int(
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    1440,
    minimum=5,
    maximum=10080,
)

SESSION_COOKIE_NAME = "kk_session"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)

#  Password helpers 

def hash_password(password: str) -> str:
    """Hash password using bcrypt directly."""
    pwd_bytes = password.encode("utf-8")
    if len(pwd_bytes) > 72:
        raise HTTPException(status_code=400, detail="Password is too long; maximum is 72 UTF-8 bytes")
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")


def get_password_hash(password: str) -> str:
    """Compatibility alias used by password-reset code."""
    return hash_password(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify password against bcrypt hash."""
    try:
        pwd_bytes = plain.encode("utf-8")
        if len(pwd_bytes) > 72:
            return False
        return bcrypt.checkpw(pwd_bytes, hashed.encode("utf-8"))
    except Exception:
        return False

#  JWT helpers 

def create_access_token(user_id: str, email: str, auth_version: int = 1) -> str:
    issued_at = datetime.utcnow()
    payload = {
        "sub": user_id,
        "email": normalize_email(email),
        "ver": int(auth_version or 1),
        "iat": issued_at,
        "jti": secrets.token_hex(16),
        "exp": issued_at + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except PyJWTError:
        return None


def normalize_email(email: str) -> str:
    """Normalize email identifiers consistently across registration and login."""

    return str(email).strip().casefold()


def token_matches_user(payload: dict, user: User) -> bool:
    """Reject tokens minted before a password reset or auth-version change."""

    return payload.get("ver") == int(user.auth_version or 1)

#  API Key helpers 

def generate_api_key() -> tuple[str, str, str]:
    """Returns (raw_key, key_hash, key_prefix)."""
    raw_key = "sc_" + secrets.token_urlsafe(40)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:11]
    return raw_key, key_hash, key_prefix


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()

#  FastAPI dependencies 

def get_current_user_jwt(
    token: Optional[str] = Depends(oauth2_scheme),
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = token or session_token
    if not token:
        raise credentials_exception
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        raise credentials_exception
    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or not user.is_active or not token_matches_user(payload, user):
        raise credentials_exception
    return user


def get_current_user_apikey(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> tuple[User, Optional[APIKey]]:
    raw_key = credentials.credentials if credentials else session_token
    if not raw_key:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # 1. Check if token is a valid user JWT session
    payload = decode_access_token(raw_key)
    if payload and payload.get("sub"):
        user = db.query(User).filter(User.id == payload["sub"], User.is_active == True).first()
        if user and token_matches_user(payload, user):
            return user, None

    # 2. Check if token is an API key
    key_hash = hash_api_key(raw_key)
    api_key = db.query(APIKey).filter(
        APIKey.key_hash == key_hash,
        APIKey.is_active == True,
    ).first()
    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid or revoked authentication credentials")

    user = db.query(User).filter(User.id == api_key.user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="Account not found or suspended")

    api_key.last_used = datetime.utcnow()
    api_key.requests_today += 1
    db.commit()
    return user, api_key

#  Business logic 

def register_user(email: str, password: str, full_name: Optional[str], db: Session) -> User:
    normalized_email = normalize_email(email)
    existing = db.query(User).filter(User.email == normalized_email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        id=str(uuid.uuid4()),
        email=normalized_email,
        hashed_password=hash_password(password),
        full_name=full_name.strip() if full_name and full_name.strip() else None,
        plan="free",
        generations=5,
        monthly_limit=5,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Email already registered") from None
    db.refresh(user)
    return user


def authenticate_user(email: str, password: str, db: Session) -> Optional[User]:
    user = db.query(User).filter(User.email == normalize_email(email)).first()
    if not user or not user.is_active or not verify_password(password, user.hashed_password):
        return None
    return user


def create_user_api_key(user: User, name: str, db: Session) -> tuple[str, APIKey]:
    existing_count = db.query(APIKey).filter(
        APIKey.user_id == user.id, APIKey.is_active == True
    ).count()
    if existing_count >= 5:
        raise HTTPException(status_code=400, detail="Maximum 5 API keys per account")

    raw_key, key_hash, key_prefix = generate_api_key()
    clean_name = name.strip() or "Default Key"
    api_key = APIKey(
        id=str(uuid.uuid4()),
        user_id=user.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=clean_name,
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

#  Integration credential encryption
# The key is validated centrally in config.py.  There is deliberately no
# source-controlled fallback: losing a development key should invalidate local
# ciphertext, while production must fail startup rather than encrypting with a
# publicly discoverable key.
_fernet = Fernet(INTEGRATION_ENCRYPTION_KEY.encode())


def encrypt_credentials(data: str) -> str:
    return _fernet.encrypt(data.encode()).decode()


def decrypt_credentials(data: str) -> str:
    return _fernet.decrypt(data.encode()).decode()
