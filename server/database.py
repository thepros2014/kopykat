"""database.py — SQLAlchemy database setup and ORM models."""
import logging
import os
from pathlib import Path
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Float, UniqueConstraint, Boolean, DateTime, Text, ForeignKey, text, inspect, event
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

from .config import STRICT_CONFIG

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if STRICT_CONFIG and not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be configured in staging and production.")
if STRICT_CONFIG and not DATABASE_URL.startswith(("postgres://", "postgresql://", "postgresql+")):
    raise RuntimeError("Staging and production require a managed PostgreSQL DATABASE_URL.")
if not DATABASE_URL:
    sqlite_path = Path(os.getenv("SQLITE_PATH", "data/kopykat.db")).expanduser()
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    DATABASE_URL = f"sqlite:///{sqlite_path.as_posix()}"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_is_sqlite = DATABASE_URL.startswith("sqlite")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite else {},
    pool_pre_ping=not _is_sqlite,
    pool_recycle=1800 if not _is_sqlite else -1,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _configure_sqlite_connection(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    def __init__(self, **kwargs):
        if "name" in kwargs and "full_name" not in kwargs:
            kwargs["full_name"] = kwargs.pop("name")
        super().__init__(**kwargs)

    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    stripe_customer_id = Column(String(50), nullable=True)
    plan = Column(String(20), default="free")
    generations = Column(Integer, default=5)
    monthly_limit = Column(Integer, default=5)
    monthly_generations = Column(Integer, default=5)
    purchased_generations = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    auth_version = Column(Integer, default=1, nullable=False)
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


class PartnerListing(Base):
    """Private state for paid dropship-partner directory placements.

    Partner contact addresses are intentionally not stored here. They are
    deployment configuration used only by the invitation job. Activation
    tokens are stored as hashes so a database read cannot be used to activate
    a listing.
    """
    __tablename__ = "partner_listings"
    partner_key = Column(String(50), primary_key=True)
    status = Column(String(30), default="pending", nullable=False)
    placement_type = Column(String(20), default="directory", nullable=False)
    placement_slot = Column(Integer, nullable=True)
    activation_id = Column(String(64), nullable=True, index=True)
    logo_url = Column(String(2_000), nullable=True)
    service_url = Column(String(2_000), nullable=True)
    billing_interval = Column(String(10), nullable=True)
    stripe_customer_id = Column(String(50), nullable=True)
    stripe_subscription_id = Column(String(50), unique=True, nullable=True)
    stripe_checkout_session_id = Column(String(100), unique=True, nullable=True)
    stripe_checkout_url = Column(String(2_000), nullable=True)
    activation_token_hash = Column(String(64), unique=True, nullable=True)
    activation_token_expires_at = Column(DateTime, nullable=True)
    invite_sent_at = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PartnerPlacementReservation(Base):
    """Atomic slot reservation used while a partner checkout is in flight.

    The composite key prevents two concurrent checkouts from purchasing the
    same paid placement. A checkout reservation expires if a provider call
    dies before the session ID is stored; active subscriptions retain their
    reservation until the signed cancellation event arrives.
    """

    __tablename__ = "partner_placement_reservations"
    placement_type = Column(String(20), primary_key=True)
    placement_slot = Column(Integer, primary_key=True)
    partner_key = Column(String(50), nullable=False)
    activation_id = Column(String(64), nullable=False)
    status = Column(String(20), default="checkout", nullable=False)
    stripe_checkout_session_id = Column(String(100), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


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

class InventoryWebhookEvent(Base):
    __tablename__ = "inventory_webhook_events"
    id = Column(String(36), primary_key=True)
    platform = Column(String(50), nullable=False)
    event_id = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("platform", "event_id", name="uq_platform_event_id"),)

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


class CustomerReview(Base):
    __tablename__ = "customer_reviews"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    customer_name = Column(String(100), nullable=False)
    customer_email = Column(String(255), nullable=True)
    product_name = Column(String(255), nullable=False)
    rating = Column(Integer, default=5, nullable=False)
    review_text = Column(Text, nullable=False)
    sentiment = Column(String(20), default="positive", nullable=False)  # positive, neutral, negative
    status = Column(String(30), default="published", nullable=False)   # published, action_needed, resolved
    draft_reply = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PriceMarginItem(Base):
    __tablename__ = "price_margin_items"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    sku = Column(String(100), nullable=False)
    product_name = Column(String(255), nullable=False)
    cogs_usd = Column(Float, default=0.0, nullable=False)
    selling_price_usd = Column(Float, default=0.0, nullable=False)
    competitor_price_usd = Column(Float, nullable=True)
    target_margin_pct = Column(Float, default=40.0, nullable=False)
    current_margin_pct = Column(Float, default=0.0, nullable=False)
    profit_per_unit_usd = Column(Float, default=0.0, nullable=False)
    status = Column(String(20), default="healthy", nullable=False)  # healthy, warning, critical
    recommendation = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserEntitlement(Base):
    __tablename__ = "user_entitlements"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    entitlement_key = Column(String(100), nullable=False)
    entitlement_type = Column(String(30), default="addon")
    active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class BrandPersona(Base):
    __tablename__ = "brand_personas"
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), unique=True, nullable=False)
    brand_name = Column(String(255), nullable=False)
    brand_voice_tone = Column(String(255), nullable=False)
    target_audience = Column(String(500), nullable=True)
    rules_and_guidelines = Column(Text, nullable=True)
    sample_copy = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class OpportunityLog(Base):
    __tablename__ = "opportunity_logs"
    id = Column(String(36), primary_key=True)
    platform = Column(String(50), nullable=False)
    post_id = Column(String(100), unique=True, nullable=False)
    post_url = Column(String(500), nullable=True)
    post_title = Column(String(500), nullable=True)
    draft_reply = Column(Text, nullable=True)
    score = Column(Integer, default=85, nullable=False)  # 1-100 buyer intent score
    alerted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

_LEGACY_COLUMN_MIGRATIONS = {
    # Existing Render databases predate some of the current ORM fields.  The
    # ORM's create_all() creates missing tables, but intentionally does not add
    # columns to tables that already exist.
    "users": {
        "plan": ("VARCHAR(20)", "'free'"),
        "generations": ("INTEGER", "5"),
        "monthly_limit": ("INTEGER", "5"),
        "monthly_generations": ("INTEGER", "5"),
        "purchased_generations": ("INTEGER", "0"),
        "is_active": ("BOOLEAN", "TRUE"),
        "is_verified": ("BOOLEAN", "FALSE"),
        "auth_version": ("INTEGER", "1"),
        "created_at": ("TIMESTAMP", "CURRENT_TIMESTAMP"),
        "updated_at": ("TIMESTAMP", "CURRENT_TIMESTAMP"),
        "custom_ai_key_encrypted": ("TEXT", None),
        "custom_ai_provider": ("VARCHAR(50)", None),
    },
    "api_keys": {
        "is_active": ("BOOLEAN", "TRUE"),
        "last_used": ("TIMESTAMP", None),
        "requests_today": ("INTEGER", "0"),
        "created_at": ("TIMESTAMP", "CURRENT_TIMESTAMP"),
    },
    "subscriptions": {
        "plan": ("VARCHAR(20)", "'free'"),
        "status": ("VARCHAR(20)", "'active'"),
        "current_period_start": ("TIMESTAMP", None),
        "current_period_end": ("TIMESTAMP", None),
        "canceled_at": ("TIMESTAMP", None),
        "created_at": ("TIMESTAMP", "CURRENT_TIMESTAMP"),
    },
    "usage_records": {
        "generations_used": ("INTEGER", "1"),
    },
    "revenue_records": {
        "amount_cents": ("INTEGER", "0"),
        "currency": ("VARCHAR(3)", "'usd'"),
        "plan": ("VARCHAR(20)", None),
        "status": ("VARCHAR(20)", "'succeeded'"),
    },
    "opportunity_logs": {
        "score": ("INTEGER", "85"),
    },
    "partner_listings": {
        "activation_id": ("VARCHAR(64)", None),
        "placement_type": ("VARCHAR(20)", "'directory'"),
        "placement_slot": ("INTEGER", None),
        "logo_url": ("VARCHAR(2000)", None),
        "service_url": ("VARCHAR(2000)", None),
    },
}


def _ensure_legacy_columns(database_engine=engine) -> list[str]:
    """Add safe, idempotent columns to databases created by older releases.

    This deliberately covers compatibility fields only.  New tables are still
    created by ``Base.metadata.create_all`` above, while required structural
    changes should continue to be introduced as explicit migrations.
    """

    inspector = inspect(database_engine)
    table_names = set(inspector.get_table_names())
    added: list[str] = []
    preparer = database_engine.dialect.identifier_preparer

    for table_name, migrations in _LEGACY_COLUMN_MIGRATIONS.items():
        if table_name not in table_names:
            continue

        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing = [
            (column_name, sql_type, default)
            for column_name, (sql_type, default) in migrations.items()
            if column_name not in existing_columns
        ]
        if not missing:
            continue

        quoted_table = preparer.quote(table_name)
        with database_engine.begin() as connection:
            for column_name, sql_type, default in missing:
                default_clause = f" DEFAULT {default}" if default is not None else ""
                connection.execute(text(
                    f"ALTER TABLE {quoted_table} ADD COLUMN "
                    f"{preparer.quote(column_name)} {sql_type}{default_clause}"
                ))
                added.append(f"{table_name}.{column_name}")

    if added:
        logger.warning("Applied legacy database column migrations: %s", ", ".join(added))
    return added


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        if STRICT_CONFIG:
            raise
        logger.warning("create_all notice: %s", e)

    try:
        inspector = inspect(engine)
        if "users" in inspector.get_table_names():
            columns = {c["name"] for c in inspector.get_columns("users")}
            if "generations" not in columns and "generations_remaining" in columns:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE users RENAME COLUMN generations_remaining TO generations"))
                columns.add("generations")

        _ensure_legacy_columns(engine)
    except Exception as e:
        if STRICT_CONFIG:
            raise
        logger.warning("Schema column inspection notice: %s", e)
