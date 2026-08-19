"""
database.py — SQLite database setup via SQLAlchemy.
All customer, subscription, API key, and usage data is stored here.
"""

import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, String, Integer, Float,
    Boolean, DateTime, Text, ForeignKey
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker, Session
from sqlalchemy.pool import StaticPool

# ── Database file lives in the same directory as this file ─────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./snapcopy.db")

# Fix for SQLAlchemy 1.4+ which dropped support for "postgres://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    poolclass=StaticPool if "sqlite" in DATABASE_URL else None,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# ── ORM Models ───────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id             = Column(String(36), primary_key=True)          # UUID
    email          = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name      = Column(String(255), nullable=True)
    stripe_customer_id = Column(String(50), nullable=True)
    plan           = Column(String(20), default="free")            # free / basic / pro / business
    credits        = Column(Integer, default=5000)                 # remaining token credits
    monthly_limit  = Column(Integer, default=5000)                 # tokens per billing cycle
    is_active      = Column(Boolean, default=True)
    is_verified    = Column(Boolean, default=False)
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    api_keys       = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    subscriptions  = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    usage_records  = relationship("UsageRecord", back_populates="user", cascade="all, delete-orphan")


class APIKey(Base):
    __tablename__ = "api_keys"

    id         = Column(String(36), primary_key=True)
    user_id    = Column(String(36), ForeignKey("users.id"), nullable=False)
    key_hash   = Column(String(64), unique=True, nullable=False)   # SHA-256 of raw key
    key_prefix = Column(String(12), nullable=False)                # first 8 chars for display
    name       = Column(String(100), default="Default Key")
    is_active  = Column(Boolean, default=True)
    last_used  = Column(DateTime, nullable=True)
    requests_today = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="api_keys")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id                     = Column(String(36), primary_key=True)
    user_id                = Column(String(36), ForeignKey("users.id"), nullable=False)
    stripe_subscription_id = Column(String(50), unique=True, nullable=True)
    stripe_price_id        = Column(String(50), nullable=True)
    plan                   = Column(String(20), nullable=False)   # basic / pro / business
    status                 = Column(String(20), default="active") # active / canceled / past_due
    current_period_start   = Column(DateTime, nullable=True)
    current_period_end     = Column(DateTime, nullable=True)
    canceled_at            = Column(DateTime, nullable=True)
    created_at             = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="subscriptions")


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id           = Column(String(36), primary_key=True)
    user_id      = Column(String(36), ForeignKey("users.id"), nullable=False)
    endpoint     = Column(String(100), nullable=False)            # e.g. "generate_copy"
    prompt_type  = Column(String(50), nullable=True)              # e.g. "product_description"
    tokens_used  = Column(Integer, default=0)
    cost_usd     = Column(Float, default=0.0)                     # cost to us in USD
    latency_ms   = Column(Integer, default=0)
    created_at   = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="usage_records")


class RevenueRecord(Base):
    """Tracks every payment event for the business owner's reporting."""
    __tablename__ = "revenue_records"

    id                 = Column(String(36), primary_key=True)
    stripe_payment_id  = Column(String(50), unique=True, nullable=True)
    user_id            = Column(String(36), nullable=True)
    amount_cents       = Column(Integer, nullable=False)           # amount in cents
    currency           = Column(String(3), default="usd")
    plan               = Column(String(20), nullable=True)
    type               = Column(String(30), nullable=False)        # subscription / credit_pack / refund
    status             = Column(String(20), default="succeeded")
    created_at         = Column(DateTime, default=datetime.utcnow)


class BlogPost(Base):
    """SEO blog posts auto-generated by the SEO engine."""
    __tablename__ = "blog_posts"

    id           = Column(String(36), primary_key=True)
    title        = Column(String(255), nullable=False)
    slug         = Column(String(255), unique=True, nullable=False)
    keyword      = Column(String(255), nullable=False)   # target SEO keyword
    meta_desc    = Column(String(160), nullable=True)    # SEO meta description
    content      = Column(Text, nullable=False)          # full HTML/markdown content
    word_count   = Column(Integer, default=0)
    published    = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)


class DripLog(Base):
    """Tracks which drip emails have been sent to each user."""
    __tablename__ = "drip_logs"

    id         = Column(String(36), primary_key=True)
    user_id    = Column(String(36), ForeignKey("users.id"), nullable=False)
    step       = Column(Integer, nullable=False)   # 1, 3, 7 (day number)
    sent_at    = Column(DateTime, default=datetime.utcnow)


class OpportunityLog(Base):
    """Tracks Reddit/forum opportunities already processed to avoid duplicates."""
    __tablename__ = "opportunity_logs"

    id           = Column(String(36), primary_key=True)
    platform     = Column(String(50), nullable=False)   # "reddit", "hackernews"
    post_id      = Column(String(100), unique=True, nullable=False)
    post_url     = Column(String(500), nullable=True)
    post_title   = Column(String(500), nullable=True)
    draft_reply  = Column(Text, nullable=True)
    alerted      = Column(Boolean, default=False)
    created_at   = Column(DateTime, default=datetime.utcnow)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_db():
    """FastAPI dependency — yields a DB session and ensures it closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Called on server startup."""
    Base.metadata.create_all(bind=engine)
