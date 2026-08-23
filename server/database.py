"""database.py — SQLAlchemy database setup and ORM models."""
import os
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Float, UniqueConstraint, Boolean, DateTime, Text, ForeignKey, text, inspect
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    # SQLite is useful only for local development. Production must explicitly configure DATABASE_URL.
    if os.getenv("ENVIRONMENT", "development").lower() in {"production", "prod"}:
        raise RuntimeError("DATABASE_URL is required in production.")
    DATABASE_URL = "sqlite:///./kopykat.db"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    stripe_customer_id = Column(String(50), nullable=True)
    plan = Column(String(20), default="free")
    generations = Column(Integer, default=5)
    monthly_limit = Column(Integer, default=5)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    custom_ai_key_encrypted = Column(Text, nullable=True)
    custom_ai_provider = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    usage_records = relationship("UsageRecord", back_populates="user", cascade="all, delete-orphan")

class APIKey(Base):
    __tablename__ = "api_keys"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    key_hash = Column(String(64), unique=True, nullable=False)
    key_prefix = Column(String(12), nullable=False)
    name = Column(String(100), default="Default Key")
    is_active = Column(Boolean, default=True)
    last_used = Column(DateTime, nullable=True)
    requests_today = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="api_keys")

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    stripe_subscription_id = Column(String(50), unique=True, nullable=True)
    stripe_price_id = Column(String(50), nullable=True)
    plan = Column(String(20), nullable=False)
    status = Column(String(20), default="active")
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    canceled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="subscriptions")

class VerificationToken(Base):
    __tablename__ = "verification_tokens"
    token = Column(String(64), primary_key=True)
    user_id = Column(String(36), nullable=False)
    token_type = Column(String(20), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class UserIntegration(Base):
    __tablename__ = "user_integrations"
    __table_args__ = (UniqueConstraint("user_id", "platform", name="uq_user_platform"),)
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False)
    platform = Column(String(50), nullable=False)
    credentials = Column(String(1000), nullable=False)
    status = Column(String(50), default="connected")
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Campaign(Base):
    __tablename__ = "campaigns"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False)
    name = Column(String(255), nullable=False)
    assets = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class PushJob(Base):
    __tablename__ = "push_jobs"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False)
    platform = Column(String(50), nullable=False)
    status = Column(String(30), default="pending")
    details = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class UsageRecord(Base):
    __tablename__ = "usage_records"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    endpoint = Column(String(100), nullable=False)
    prompt_type = Column(String(50), nullable=True)
    generations_used = Column(Integer, default=1)
    tokens_used = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    latency_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="usage_records")

class RevenueRecord(Base):
    __tablename__ = "revenue_records"
    id = Column(String(36), primary_key=True)
    stripe_payment_id = Column(String(50), unique=True, nullable=True)
    user_id = Column(String(36), nullable=True)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(3), default="usd")
    plan = Column(String(20), nullable=True)
    type = Column(String(30), nullable=False)
    status = Column(String(20), default="succeeded")
    created_at = Column(DateTime, default=datetime.utcnow)

class StripeEvent(Base):
    __tablename__ = "stripe_events"
    event_id = Column(String(64), primary_key=True)
    event_type = Column(String(100), nullable=False)
    processed_at = Column(DateTime, default=datetime.utcnow)

class CustomConnector(Base):
    """Stores discovered connector specs for the Universal Connector Engine.
    Credentials are NEVER stored in this table — they live in UserIntegration.
    """
    __tablename__ = "custom_connectors"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False)
    platform_name = Column(String(120), nullable=False)
    source_url = Column(String(2000), nullable=False)
    base_url = Column(String(2000), nullable=False)
    spec = Column(Text, nullable=False)           # JSON connector spec (no credentials)
    authentication_modes = Column(String(200), nullable=True)  # comma-separated
    operation_count = Column(Integer, default=0)
    status = Column(String(30), default="draft")  # draft / validated / active / disabled
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ConnectorAuditLog(Base):
    __tablename__ = "connector_audit_logs"
    id = Column(String(36), primary_key=True)
    connector_id = Column(String(36), nullable=False)
    user_id = Column(String(36), nullable=False)
    operation_name = Column(String(120), nullable=False)
    status = Column(String(30), nullable=False)  # success / failed / blocked
    status_code = Column(Integer, nullable=True)
    details = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class BlogPost(Base):
    __tablename__ = "blog_posts"
    id = Column(String(36), primary_key=True)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False)
    keyword = Column(String(255), nullable=False)
    meta_desc = Column(String(160), nullable=True)
    content = Column(Text, nullable=False)
    word_count = Column(Integer, default=0)
    published = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class DripLog(Base):
    __tablename__ = "drip_logs"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    step = Column(Integer, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)


class CompetitorAudit(Base):
    __tablename__ = "competitor_audits"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False)
    product_name = Column(String(255), nullable=False)
    competitor_name = Column(String(255), nullable=False)
    extracted_flaws = Column(Text, nullable=False)
    counter_copy = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    sku = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    total_stock = Column(Integer, default=0, nullable=False)
    platform_stock = Column(Text, default="{}", nullable=False)  # JSON string of {platform: qty}
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class InventorySyncLog(Base):
    __tablename__ = "inventory_sync_logs"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    sku = Column(String(100), nullable=False)
    trigger_platform = Column(String(50), nullable=False)
    quantity_change = Column(Integer, nullable=False)
    new_quantity = Column(Integer, nullable=False)
    fanout_results = Column(Text, default="{}", nullable=False)  # JSON string of {platform: status}
    created_at = Column(DateTime, default=datetime.utcnow)

class OpportunityLog(Base):
    __tablename__ = "opportunity_logs"
    id = Column(String(36), primary_key=True)
    platform = Column(String(50), nullable=False)
    post_id = Column(String(100), unique=True, nullable=False)
    post_url = Column(String(500), nullable=True)
    post_title = Column(String(500), nullable=True)
    draft_reply = Column(Text, nullable=True)
    alerted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    if "users" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("users")}
        with engine.begin() as conn:
            if "generations" not in columns and "generations_remaining" in columns:
                conn.execute(text("ALTER TABLE users RENAME COLUMN generations_remaining TO generations"))
            elif "generations" not in columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN generations INTEGER DEFAULT 5"))
    if "usage_records" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("usage_records")}
        if "generations_used" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE usage_records ADD COLUMN generations_used INTEGER DEFAULT 1"))
