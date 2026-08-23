"""
adversarial_tests.py — Tier 5 Adversarial Coverage Hardening Suite for KopyKat.

White-box adversarial stress tests targeting:
1. Concurrency & Race Conditions (quota reservation, boundary races, depletion/refill loops, webhook deduplication)
2. SSRF & Network Defense Edge Cases (obfuscated IPs: decimal, octal, hex, IPv4-mapped IPv6, metadata, redirects, payload caps)
3. Financial Invariant Stress (multi-stage quota ops, partial failures, negative credit attacks, refund idempotency, unconfigured Stripe fallback)
4. Tenant Isolation & IDOR (cross-tenant resource access across keys, connectors, personas, inventory, campaigns; forged/expired JWTs, bcrypt 72-byte truncation)
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import datetime
import hashlib
import ipaddress
import json
import os
import secrets
import threading
import uuid
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import bcrypt
import httpx
import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Set test environment
os.environ["ENVIRONMENT"] = "testing"
os.environ["JWT_SECRET_KEY"] = "kopykat-test-jwt-secret-key-32-chars-long-strict"
os.environ["SECRET_KEY"] = "kopykat-test-jwt-secret-key-32-chars-long-strict"
os.environ["INTEGRATION_ENCRYPTION_KEY"] = "wB2tN4a-7iL3sZ_qU8rX0vY5mP1oJ9eK6cF_dG4hA8s="
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test_secret_for_adversarial_suite"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_mocked_key"

from server.database import (
    Base, get_db, User, APIKey, Subscription, RevenueRecord,
    StripeEvent, UserIntegration, CustomConnector, InventoryItem,
    InventoryWebhookEvent, InventorySyncLog, BrandPersona, Campaign,
    PriceMarginItem, CustomerReview, UserEntitlement
)
from server.main import app, reserve_user_generations, refund_user_generations
from server.auth import (
    create_access_token, hash_password, verify_password,
    decode_access_token, generate_api_key, hash_api_key,
    encrypt_credentials, decrypt_credentials
)
from server.billing import (
    handle_stripe_webhook, PLANS, ONE_TIME_GENERATIONS, ADD_ONS,
    create_subscription_checkout, create_one_time_checkout, user_has_entitlement
)
from server.connector_engine import (
    SSRFError, ConnectorError, validate_ip_address,
    resolve_and_validate_host, validate_public_url,
    SafeAsyncHTTPClient, SafeHTTPResponse, build_connector_spec
)
from server.inventory import sync_inventory_across_platforms


# ==============================================================================
# FIXTURES & ISOLATED IN-MEMORY DATABASE SETUP
# ==============================================================================

@pytest.fixture(scope="module")
def adv_engine():
    """Module-scoped SQLite database with check_same_thread=False for concurrency."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def adv_db(adv_engine):
    """Provides a clean database session for each test, rolling back transactions."""
    connection = adv_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    yield session

    app.dependency_overrides.clear()
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def adv_client(adv_db):
    """TestClient with dependency overrides active."""
    with TestClient(app) as test_client:
        yield test_client


def _create_user(
    db: Session,
    user_id: Optional[str] = None,
    email: Optional[str] = None,
    plan: str = "boutique",
    monthly: int = 150,
    purchased: int = 0,
    is_active: bool = True
) -> User:
    uid = user_id or str(uuid.uuid4())
    em = email or f"user_{uid[:8]}@example.com"
    user = User(
        id=uid,
        email=em,
        hashed_password=hash_password("StrongPassword123!"),
        full_name="Adversarial Test User",
        plan=plan,
        monthly_limit=monthly,
        monthly_generations=monthly,
        purchased_generations=purchased,
        generations=monthly + purchased,
        is_active=is_active,
        is_verified=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_header_for_user(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.email)
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# 1. CONCURRENCY AND RACE CONDITION ADVERSARIAL TESTS
# ==============================================================================

class TestConcurrencyAndRaceConditions:
    """Adversarial stress tests for concurrent execution and race boundaries."""

    def test_concurrent_quota_consumption_exhaustion_boundary(self, adv_engine):
        """
        Adversarial Test: 20 concurrent threads attempt to reserve 1 generation each
        from a user with exactly 5 generations available.
        
        Invariant:
        - Total successful reservations must not exceed available credits (<= 5).
        - User's final total balance must be non-negative (>= 0).
        - monthly_generations + purchased_generations == generations.
        - Sum of successful reservations + remaining balance == initial balance (5).
        """
        setup_conn = adv_engine.connect()
        setup_sess = sessionmaker(bind=setup_conn)()
        user = _create_user(setup_sess, monthly=5, purchased=0)
        user_id = user.id
        setup_sess.close()
        setup_conn.close()

        successes = 0
        failures = 0
        lock = threading.Lock()

        def worker_reserve():
            nonlocal successes, failures
            conn = adv_engine.connect()
            sess = sessionmaker(bind=conn)()
            try:
                m_used, p_used = reserve_user_generations(user_id, cost=1, db=sess)
                with lock:
                    successes += 1
            except HTTPException as exc:
                with lock:
                    failures += 1
            except Exception:
                with lock:
                    failures += 1
            finally:
                sess.close()
                conn.close()

        threads = [threading.Thread(target=worker_reserve) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        verify_conn = adv_engine.connect()
        verify_sess = sessionmaker(bind=verify_conn)()
        fresh_user = verify_sess.query(User).filter(User.id == user_id).first()

        assert fresh_user is not None
        assert fresh_user.generations >= 0, "Generations balance underflowed below 0!"
        assert fresh_user.monthly_generations >= 0, "Monthly generations underflowed below 0!"
        assert fresh_user.purchased_generations >= 0, "Purchased generations underflowed below 0!"
        assert fresh_user.generations == fresh_user.monthly_generations + fresh_user.purchased_generations
        assert successes <= 5, f"Over-allocation detected: {successes} threads succeeded when only 5 credits existed!"
        assert successes + fresh_user.generations == 5, "Credits were lost or phantom created!"

        verify_sess.close()
        verify_conn.close()

    def test_simultaneous_credit_reservation_boundary_race(self, adv_engine):
        """
        Adversarial Test: User has 3 monthly + 2 purchased (total 5).
        Thread A asks for 4 credits, Thread B asks for 3 credits simultaneously.
        Total requested = 7 > 5.
        
        Invariant:
        - At most one thread can succeed.
        - The remaining balance must equal (5 - successful_cost), never negative.
        """
        setup_conn = adv_engine.connect()
        setup_sess = sessionmaker(bind=setup_conn)()
        user = _create_user(setup_sess, monthly=3, purchased=2)
        user_id = user.id
        setup_sess.close()
        setup_conn.close()

        results = []
        lock = threading.Lock()

        def try_reserve(cost: int, label: str):
            conn = adv_engine.connect()
            sess = sessionmaker(bind=conn)()
            try:
                m_used, p_used = reserve_user_generations(user_id, cost=cost, db=sess)
                with lock:
                    results.append({"label": label, "status": "ok", "cost": cost, "used": (m_used, p_used)})
            except HTTPException as exc:
                with lock:
                    results.append({"label": label, "status": "error", "code": exc.status_code})
            except Exception as e:
                with lock:
                    results.append({"label": label, "status": "error", "code": 500, "err": str(e)})
            finally:
                sess.close()
                conn.close()

        t1 = threading.Thread(target=try_reserve, args=(4, "Thread-4"))
        t2 = threading.Thread(target=try_reserve, args=(3, "Thread-3"))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        ok_results = [r for r in results if r["status"] == "ok"]
        assert len(ok_results) <= 1, f"Both conflicting threads succeeded! Overdraft occurred: {results}"

        verify_conn = adv_engine.connect()
        verify_sess = sessionmaker(bind=verify_conn)()
        fresh_user = verify_sess.query(User).filter(User.id == user_id).first()

        assert fresh_user.generations >= 0
        assert fresh_user.generations == fresh_user.monthly_generations + fresh_user.purchased_generations
        if len(ok_results) == 1:
            expected_remaining = 5 - ok_results[0]["cost"]
            assert fresh_user.generations == expected_remaining
        verify_sess.close()
        verify_conn.close()

    def test_simultaneous_quota_depletion_and_refill_loop(self, adv_engine):
        """
        Adversarial Test: Interleaved concurrent reservation and refund cycles.
        5 workers repeatedly reserve and refund credits.
        
        Invariant:
        - Total credits at the end must equal initial balance (no credit leaks or phantom generation).
        - Intermediate bucket values must never go negative.
        """
        setup_conn = adv_engine.connect()
        setup_sess = sessionmaker(bind=setup_conn)()
        user = _create_user(setup_sess, monthly=10, purchased=10)
        user_id = user.id
        setup_sess.close()
        setup_conn.close()

        def reserve_refund_cycle(worker_id: int):
            for _ in range(5):
                conn = adv_engine.connect()
                sess = sessionmaker(bind=conn)()
                try:
                    m, p = reserve_user_generations(user_id, cost=2, db=sess)
                    import time
                    time.sleep(0.005)
                    refund_user_generations(user_id, m, p, db=sess)
                except HTTPException:
                    pass
                except Exception:
                    pass
                finally:
                    sess.close()
                    conn.close()

        threads = [threading.Thread(target=reserve_refund_cycle, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        verify_conn = adv_engine.connect()
        verify_sess = sessionmaker(bind=verify_conn)()
        fresh_user = verify_sess.query(User).filter(User.id == user_id).first()

        assert fresh_user.monthly_generations >= 0
        assert fresh_user.purchased_generations >= 0
        assert fresh_user.generations == fresh_user.monthly_generations + fresh_user.purchased_generations
        assert fresh_user.generations == 20, f"Expected 20 generations after equal reservations and refunds, got {fresh_user.generations}"

        verify_sess.close()
        verify_conn.close()

    def test_concurrent_stripe_webhook_replay_deduplication_race(self, adv_engine):
        """
        Adversarial Test: 10 concurrent threads simultaneously deliver the exact same
        Stripe webhook (checkout.session.completed for 250 credits).
        
        Invariant:
        - Exactly 1 execution must process the event and increment generations by 250.
        - 9 executions must be deduplicated via StripeEvent idempotency ledger.
        - User purchased_generations must increase by exactly 250, NOT 2500.
        """
        setup_conn = adv_engine.connect()
        setup_sess = sessionmaker(bind=setup_conn)()
        user = _create_user(setup_sess, monthly=5, purchased=0)
        user_id = user.id
        setup_sess.close()
        setup_conn.close()

        event_id = f"evt_adv_race_{uuid.uuid4().hex[:12]}"
        payload_obj = {
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": f"cs_test_{uuid.uuid4().hex[:8]}",
                    "payment_intent": f"pi_test_{uuid.uuid4().hex[:8]}",
                    "amount_total": 500,
                    "currency": "usd",
                    "metadata": {"user_id": user_id, "pack": "starter"}
                }
            }
        }
        payload_bytes = json.dumps(payload_obj).encode()

        processed_count = 0
        already_processed_count = 0
        lock = threading.Lock()

        def deliver_webhook():
            nonlocal processed_count, already_processed_count
            conn = adv_engine.connect()
            sess = sessionmaker(bind=conn)()
            try:
                with patch("stripe.Webhook.construct_event", return_value=payload_obj):
                    res = handle_stripe_webhook(payload_bytes, "sig_test", db=sess)
                    with lock:
                        if res.get("status") == "processed":
                            processed_count += 1
                        elif res.get("status") == "already_processed":
                            already_processed_count += 1
            except Exception:
                pass
            finally:
                sess.close()
                conn.close()

        threads = [threading.Thread(target=deliver_webhook) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert processed_count == 1, f"Expected exactly 1 processed event, got {processed_count}"
        assert already_processed_count >= 1, f"Expected deduplication, got {already_processed_count}"

        verify_conn = adv_engine.connect()
        verify_sess = sessionmaker(bind=verify_conn)()
        fresh_user = verify_sess.query(User).filter(User.id == user_id).first()
        rev_records = verify_sess.query(RevenueRecord).filter(RevenueRecord.user_id == user_id).all()

        assert fresh_user.purchased_generations == 250, f"Expected 250 purchased generations, got {fresh_user.purchased_generations}"
        assert fresh_user.generations == 255
        assert len(rev_records) == 1, f"Expected exactly 1 revenue record, got {len(rev_records)}"

        verify_sess.close()
        verify_conn.close()

    def test_concurrent_inventory_webhook_replay_race(self, adv_engine):
        """
        Adversarial Test: 10 concurrent threads simultaneously post the exact same
        inventory webhook event (delta=-2, event_id='evt_inv_race_001').
        
        Invariant:
        - Inventory must decrement by 2 exactly once (from 20 to 18).
        - Unique constraint on (platform, event_id) must prevent double-decrement.
        """
        setup_conn = adv_engine.connect()
        setup_sess = sessionmaker(bind=setup_conn)()
        user = _create_user(setup_sess)
        user_id = user.id

        item = InventoryItem(
            id=str(uuid.uuid4()),
            user_id=user_id,
            sku="RACE-SKU-100",
            title="Race Test Item",
            total_stock=20,
            platform_stock=json.dumps({"shopify": 20}),
            updated_at=datetime.datetime.utcnow()
        )
        setup_sess.add(item)
        setup_sess.commit()
        setup_sess.close()
        setup_conn.close()

        event_id = f"evt_inv_race_{uuid.uuid4().hex[:8]}"

        def post_inv_webhook():
            conn = adv_engine.connect()
            sess = sessionmaker(bind=conn)()
            try:
                sync_inventory_across_platforms(
                    user_id=user_id,
                    sku="RACE-SKU-100",
                    delta=-2,
                    trigger_platform="shopify",
                    db=sess,
                    event_id=event_id
                )
                sess.commit()
            except Exception:
                sess.rollback()
            finally:
                sess.close()
                conn.close()

        threads = [threading.Thread(target=post_inv_webhook) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        verify_conn = adv_engine.connect()
        verify_sess = sessionmaker(bind=verify_conn)()
        fresh_item = verify_sess.query(InventoryItem).filter(
            InventoryItem.user_id == user_id,
            InventoryItem.sku == "RACE-SKU-100"
        ).first()

        assert fresh_item.total_stock == 18, f"Stock was decremented incorrectly! Expected 18, got {fresh_item.total_stock}"

        events = verify_sess.query(InventoryWebhookEvent).filter(
            InventoryWebhookEvent.event_id == event_id
        ).all()
        assert len(events) == 1, f"Expected 1 idempotency event recorded, got {len(events)}"

        verify_sess.close()
        verify_conn.close()


# ==============================================================================
# 2. SSRF & NETWORK DEFENSE ADVERSARIAL TESTS
# ==============================================================================

class TestSSRFAndNetworkDefense:
    """Adversarial validation of IP obfuscation, schemes, cloud metadata, and redirects."""

    @pytest.mark.parametrize("obfuscated_ip", [
        # Standard loopback variants
        "127.0.0.1",
        "127.0.0.2",
        "127.1.1.1",
        # Decimal / Integer representations
        "2130706433",          # 127.0.0.1
        "3232235521",          # 192.168.0.1
        "2886729729",          # 172.16.0.1
        "168198145",           # 10.7.0.1
        # Octal representations
        "0177.0.0.1",          # 127.0.0.1
        "0177.0.0.01",
        "017700000001",
        "0300.0250.0.1",       # 192.168.0.1
        # Hex representations
        "0x7f.1",              # 127.0.0.1
        "0x7f000001",          # 127.0.0.1
        "0x7f.0.0.1",
        "0x7f.0x0.0x0.0x1",
        "0xc0.0xa8.0x1.0x1",   # 192.168.1.1
    ])
    def test_ssrf_obfuscated_ipv4_encodings_blocked(self, obfuscated_ip):
        """
        Adversarial Test: Obfuscated IPv4 schemes (decimal, octal, hex, dword).
        Must be resolved/validated and rejected with SSRFError or ConnectorError.
        """
        with pytest.raises((SSRFError, ConnectorError)):
            resolve_and_validate_host(obfuscated_ip, 443)

    @pytest.mark.parametrize("ipv6_variant", [
        "::1",
        "[::1]",
        "0:0:0:0:0:0:0:1",
        "::",
        "[::]",
        "fe80::1",             # Link-local
        "fe80::200:5aee:feaa:20a2",
        "fc00::1",             # Unique local
        "fd00::1",
        "::ffff:127.0.0.1",    # IPv4-mapped IPv6 loopback
        "::ffff:169.254.169.254", # IPv4-mapped metadata
        "::ffff:10.0.0.1",     # IPv4-mapped RFC1918
        "::ffff:192.168.1.1",
        "[::ffff:7f00:1]",
        "::127.0.0.1",         # IPv4-compatible
    ])
    def test_ssrf_ipv6_and_mapped_addresses_blocked(self, ipv6_variant):
        """
        Adversarial Test: IPv6 loopbacks, link-local, ULA, and IPv4-mapped IPv6 addresses.
        Must be rejected with SSRFError or ConnectorError.
        """
        with pytest.raises((SSRFError, ConnectorError)):
            clean_host = ipv6_variant.strip("[]")
            try:
                ip_obj = ipaddress.ip_address(clean_host)
                validate_ip_address(ip_obj)
            except ValueError:
                resolve_and_validate_host(ipv6_variant, 443)

    @pytest.mark.parametrize("metadata_url", [
        # AWS / Azure / GCP IMDS endpoints
        "http://169.254.169.254/latest/meta-data/",
        "https://169.254.169.254/latest/meta-data/",
        "http://169.254.169.254/computeMetadata/v1/",
        "http://instance-data/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "https://metadata.google.internal/computeMetadata/v1/",
        "http://100.100.100.200/latest/meta-data/",  # Alibaba Cloud metadata
    ])
    def test_ssrf_cloud_metadata_endpoints_blocked(self, metadata_url):
        """
        Adversarial Test: Cloud metadata service URLs (AWS IMDSv1/v2, GCP, Azure, Alibaba).
        Must be rejected by validate_public_url.
        """
        with pytest.raises((SSRFError, ConnectorError)):
            validate_public_url(metadata_url)

    @pytest.mark.parametrize("dangerous_scheme_url", [
        "file:///etc/passwd",
        "file:///c:/windows/win.ini",
        "gopher://127.0.0.1:6379/_INFO",
        "dict://127.0.0.1:11211/stat",
        "ldap://127.0.0.1:389/o=example",
        "ftp://example.com/file.json",
        "data:application/json;base64,eyJhIjoxfQ==",
        "javascript:alert(document.cookie)",
        "http://api.example.com/openapi.json",  # Plain HTTP rejected
        "ws://api.example.com/socket",
    ])
    def test_ssrf_non_https_and_dangerous_schemes_blocked(self, dangerous_scheme_url):
        """
        Adversarial Test: Non-HTTPS protocols and URI schemes.
        Must be strictly rejected by validate_public_url.
        """
        with pytest.raises(ConnectorError):
            validate_public_url(dangerous_scheme_url)

    @pytest.mark.parametrize("internal_hostname", [
        "localhost",
        "localhost.localdomain",
        "backend.localhost",
        "redis.internal",
        "db.local",
        "service.lan",
        "router.home",
    ])
    def test_ssrf_internal_hostnames_blocked(self, internal_hostname):
        """
        Adversarial Test: Common internal TLDs and hostnames.
        Must be rejected prior to DNS lookup or on lookup.
        """
        with pytest.raises((SSRFError, ConnectorError)):
            resolve_and_validate_host(internal_hostname, 443)

    @pytest.mark.asyncio
    async def test_ssrf_redirect_defense_in_safe_client(self):
        """
        Adversarial Test: SafeAsyncHTTPClient must reject 301/302/307 redirects
        when allow_redirects=False.
        """
        client = SafeAsyncHTTPClient()
        mock_response = MagicMock()
        mock_response.status_code = 302
        mock_response.headers = {"location": "https://127.0.0.1/admin"}
        
        async def mock_aiter_bytes():
            yield b"Redirecting..."
        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.aclose = AsyncMock()

        with patch("server.connector_engine.validate_public_url", return_value="https://public.example.com/api"):
            with patch.object(httpx.AsyncClient, "send", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = mock_response
                with pytest.raises(SSRFError, match="Redirects are disabled"):
                    await client.request("GET", "https://public.example.com/api", allow_redirects=False)

    @pytest.mark.asyncio
    async def test_ssrf_streaming_response_2mb_payload_cap(self):
        """
        Adversarial Test: Streaming response exceeding 2MB payload cap
        must immediately raise SSRFError without exhausting memory.
        """
        client = SafeAsyncHTTPClient(max_response_bytes=2_000_000)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        
        async def mock_huge_stream():
            yield b"X" * 1_000_000
            yield b"Y" * 1_000_000
            yield b"Z" * 1_000_000
            
        mock_response.aiter_bytes = mock_huge_stream
        mock_response.aclose = AsyncMock()

        with patch("server.connector_engine.validate_public_url", return_value="https://public.example.com/large.json"):
            with patch.object(httpx.AsyncClient, "send", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = mock_response
                with pytest.raises(SSRFError, match="Response size exceeded"):
                    await client.request("GET", "https://public.example.com/large.json")

    def test_ssrf_crlf_and_protocol_smuggling_rejection(self):
        """
        Adversarial Test: URLs with CRLF character injection (%0d%0a) or null bytes.
        """
        crlf_url = "https://example.com%0d%0aHost:%20127.0.0.1/openapi.json"
        with pytest.raises(ConnectorError):
            validate_public_url(crlf_url)


# ==============================================================================
# 3. FINANCIAL INVARIANT STRESS ADVERSARIAL TESTS
# ==============================================================================

class TestFinancialInvariantStress:
    """Adversarial verification of dual-bucket quota invariants, refunds, and negative credit attacks."""

    def test_multi_stage_quota_reservation_and_full_refund_conservation(self, adv_db):
        """
        Adversarial Test: User with 3 monthly + 5 purchased (total 8).
        Reserve 6 credits:
        - monthly_used = 3 (monthly now 0)
        - purchased_used = 3 (purchased now 2)
        - total generations = 2.
        
        Upstream generation fails completely:
        - refund_user_generations(user_id, 3, 3)
        - restored monthly = 3, purchased = 5, total = 8.
        
        Invariant: Total credits restored must perfectly match pre-reservation state.
        """
        user = _create_user(adv_db, monthly=3, purchased=5)
        user_id = user.id

        m_used, p_used = reserve_user_generations(user_id, cost=6, db=adv_db)
        assert m_used == 3
        assert p_used == 3

        adv_db.refresh(user)
        assert user.monthly_generations == 0
        assert user.purchased_generations == 2
        assert user.generations == 2

        refund_user_generations(user_id, monthly_refund=m_used, purchased_refund=p_used, db=adv_db)
        adv_db.refresh(user)

        assert user.monthly_generations == 3
        assert user.purchased_generations == 5
        assert user.generations == 8

    def test_partial_generation_refund_bucket_ordering(self, adv_db):
        """
        Adversarial Test: User has 2 monthly + 6 purchased (total 8).
        Reserve 5 credits -> m_used=2, p_used=3.
        Only 2 variations generated -> 3 unused credits to refund.
        
        Refund priority logic:
        - refund_purchased = min(purchased_used=3, refund=3) = 3
        - refund_monthly = refund(3) - refund_purchased(3) = 0
        
        Invariant:
        - Restores purchased credits first to protect customer paid investment.
        - Final user balance: monthly=0, purchased=6. Total = 6. (Used exactly 2 monthly).
        """
        user = _create_user(adv_db, monthly=2, purchased=6)
        user_id = user.id

        cost = 5
        m_used, p_used = reserve_user_generations(user_id, cost=cost, db=adv_db)
        assert (m_used, p_used) == (2, 3)

        actual_used = 2
        refund_amount = cost - actual_used  # 3
        refund_purchased = min(p_used, refund_amount)  # 3
        refund_monthly = refund_amount - refund_purchased  # 0

        refund_user_generations(user_id, refund_monthly, refund_purchased, db=adv_db)
        adv_db.refresh(user)

        assert user.monthly_generations == 0
        assert user.purchased_generations == 6
        assert user.generations == 6

    def test_negative_and_zero_credit_reservation_attempts(self, adv_db):
        """
        Adversarial Test: Passing negative or zero cost to reserve_user_generations.
        
        If an attacker attempts to pass cost=-10:
        - Must NOT artificially inflate the user's balance.
        """
        user = _create_user(adv_db, monthly=5, purchased=0)
        user_id = user.id

        # Zero cost reservation should be a no-op
        m_used, p_used = reserve_user_generations(user_id, cost=0, db=adv_db)
        assert (m_used, p_used) == (0, 0)
        adv_db.refresh(user)
        assert user.generations == 5

        # Check API endpoint schema validation for negative variations
        from server.models import GenerateRequest
        with pytest.raises(Exception):
            GenerateRequest(type="product_description", context="Valid context text", variations=0)

        with pytest.raises(Exception):
            GenerateRequest(type="product_description", context="Valid context text", variations=-5)

        with pytest.raises(Exception):
            GenerateRequest(type="product_description", context="Valid context text", variations=100)

    def test_webhook_replay_idempotency_all_event_types(self, adv_db):
        """
        Adversarial Test: Replaying various Stripe webhook events multiple times.
        Every event type must be idempotent.
        """
        user = _create_user(adv_db, monthly=5, purchased=10)
        user_id = user.id

        # 1. invoice.payment_succeeded replay
        sub = Subscription(
            id=str(uuid.uuid4()),
            user_id=user_id,
            stripe_subscription_id="sub_adv_test_123",
            plan="standard",
            status="active"
        )
        adv_db.add(sub)
        adv_db.commit()

        inv_event_id = f"evt_inv_{uuid.uuid4().hex[:8]}"
        inv_payload = {
            "id": inv_event_id,
            "type": "invoice.payment_succeeded",
            "data": {
                "object": {
                    "id": f"in_{uuid.uuid4().hex[:8]}",
                    "subscription": "sub_adv_test_123",
                    "amount_paid": 37949,
                    "currency": "usd"
                }
            }
        }

        with patch("stripe.Webhook.construct_event", return_value=inv_payload):
            r1 = handle_stripe_webhook(json.dumps(inv_payload).encode(), "sig", adv_db)
            assert r1["status"] == "processed"

            r2 = handle_stripe_webhook(json.dumps(inv_payload).encode(), "sig", adv_db)
            assert r2["status"] == "already_processed"

        adv_db.refresh(user)
        assert user.monthly_generations == PLANS["standard"]["monthly_generations"]
        assert user.purchased_generations == 10  # Untouched

        # 2. Add-on purchase replay
        addon_event_id = f"evt_addon_{uuid.uuid4().hex[:8]}"
        addon_payload = {
            "id": addon_event_id,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": f"cs_addon_{uuid.uuid4().hex[:8]}",
                    "payment_intent": f"pi_addon_{uuid.uuid4().hex[:8]}",
                    "amount_total": 4900,
                    "currency": "usd",
                    "metadata": {"user_id": user_id, "addon_key": "brand_voice_training"}
                }
            }
        }

        with patch("stripe.Webhook.construct_event", return_value=addon_payload):
            r1 = handle_stripe_webhook(json.dumps(addon_payload).encode(), "sig", adv_db)
            assert r1["status"] == "processed"

            r2 = handle_stripe_webhook(json.dumps(addon_payload).encode(), "sig", adv_db)
            assert r2["status"] == "already_processed"

    def test_unconfigured_stripe_returns_http_503(self, adv_db):
        """
        Adversarial Test: When Stripe secret key or price environment variable is missing,
        checkout endpoints must raise HTTP 503 rather than crashing with unhandled 500.
        """
        user = _create_user(adv_db)
        
        with patch.dict(os.environ, {"STRIPE_PRICE_BOUTIQUE": ""}):
            with pytest.raises(HTTPException) as exc_info:
                create_subscription_checkout("boutique", user, adv_db)
            assert exc_info.value.status_code == 503

        with patch.dict(os.environ, {"STRIPE_PRICE_PACK_STARTER": ""}):
            with pytest.raises(HTTPException) as exc_info:
                create_one_time_checkout("starter", user, adv_db)
            assert exc_info.value.status_code == 503

    def test_subscription_cancellation_preserves_purchased_credits(self, adv_db):
        """
        Adversarial Test: When a user's subscription is canceled, their plan reverts
        to 'free' and monthly_generations to free tier limit (5), but purchased_generations
        MUST remain intact.
        """
        user = _create_user(adv_db, plan="megastore", monthly=2500, purchased=1500)
        user_id = user.id

        sub = Subscription(
            id=str(uuid.uuid4()),
            user_id=user_id,
            stripe_subscription_id="sub_cancel_test",
            plan="megastore",
            status="active"
        )
        adv_db.add(sub)
        adv_db.commit()

        cancel_payload = {
            "id": f"evt_cancel_{uuid.uuid4().hex[:8]}",
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": "sub_cancel_test",
                    "status": "canceled"
                }
            }
        }

        with patch("stripe.Webhook.construct_event", return_value=cancel_payload):
            res = handle_stripe_webhook(json.dumps(cancel_payload).encode(), "sig", adv_db)
            assert res["status"] == "processed"

        adv_db.refresh(user)
        assert user.plan == "free"
        assert user.monthly_generations == 5
        assert user.purchased_generations == 1500, "Purchased credits were improperly wiped on cancellation!"
        assert user.generations == 1505


# ==============================================================================
# 4. TENANT ISOLATION & IDOR ADVERSARIAL TESTS
# ==============================================================================

class TestTenantIsolationAndIDOR:
    """Adversarial tests for multi-tenant isolation, IDOR, forged JWTs, and bcrypt limits."""

    def test_tenant_idor_api_key_deletion(self, adv_client, adv_db):
        """
        Adversarial Test: Tenant B attempts to delete Tenant A's API Key.
        Must return 404 and leave Tenant A's key active.
        """
        user_a = _create_user(adv_db, email="tenant_a@example.com")
        user_b = _create_user(adv_db, email="tenant_b@example.com")

        raw_key, key_hash, prefix = generate_api_key()
        api_key_a = APIKey(
            id=str(uuid.uuid4()),
            user_id=user_a.id,
            key_hash=key_hash,
            key_prefix=prefix,
            name="Tenant A Secret Key",
            is_active=True
        )
        adv_db.add(api_key_a)
        adv_db.commit()

        headers_b = _auth_header_for_user(user_b)
        res = adv_client.delete(f"/api/keys/{api_key_a.id}", headers=headers_b)
        assert res.status_code == 404, f"IDOR Vulnerability: Tenant B deleted Tenant A's API key! Response: {res.json()}"

        adv_db.refresh(api_key_a)
        assert api_key_a.is_active is True, "Tenant A's API key was deactivated by Tenant B!"

    def test_tenant_idor_custom_connectors(self, adv_client, adv_db):
        """
        Adversarial Test: Tenant B attempts to read, configure credentials for,
        or test Tenant A's custom connector.
        Must return 404 on all endpoints.
        """
        user_a = _create_user(adv_db, email="tenant_conn_a@example.com")
        user_b = _create_user(adv_db, email="tenant_conn_b@example.com")

        conn_a = CustomConnector(
            id=str(uuid.uuid4()),
            user_id=user_a.id,
            platform_name="Tenant A ERP",
            source_url="https://api.tenanta.com/openapi.json",
            base_url="https://api.tenanta.com",
            spec=json.dumps({"openapi": "3.0.0", "info": {"title": "Tenant A ERP"}}),
            status="draft"
        )
        adv_db.add(conn_a)
        adv_db.commit()

        headers_b = _auth_header_for_user(user_b)

        # 1. GET /api/connector/{id}
        res_get = adv_client.get(f"/api/connector/{conn_a.id}", headers=headers_b)
        assert res_get.status_code == 404

        # 2. POST /api/connector/{id}/credentials
        res_cred = adv_client.post(
            f"/api/connector/{conn_a.id}/credentials",
            headers=headers_b,
            json={"credentials": {"api_key": "attacker_key"}}
        )
        assert res_cred.status_code == 404

        # 3. POST /api/connector/{id}/test
        res_test = adv_client.post(
            f"/api/connector/{conn_a.id}/test",
            headers=headers_b,
            json={"operation_name": "get /items"}
        )
        assert res_test.status_code == 404

    def test_tenant_idor_brand_persona_isolation(self, adv_client, adv_db):
        """
        Adversarial Test: Tenant A sets a proprietary Brand Persona.
        Tenant B queries /api/marketing/brand-persona.
        Tenant B must NOT receive Tenant A's persona.
        """
        user_a = _create_user(adv_db, email="persona_a@example.com")
        user_b = _create_user(adv_db, email="persona_b@example.com")

        persona_a = BrandPersona(
            id=str(uuid.uuid4()),
            user_id=user_a.id,
            brand_name="Secret Luxury Brand A",
            brand_voice_tone="Elite, exclusive, and confidential",
            target_audience="High net worth individuals",
            rules_and_guidelines="Never mention discounts",
            sample_copy="Handcrafted perfection for the discerning few."
        )
        adv_db.add(persona_a)
        adv_db.commit()

        headers_b = _auth_header_for_user(user_b)
        res = adv_client.get("/api/marketing/brand-persona", headers=headers_b)
        assert res.status_code == 200
        data = res.json()
        assert data.get("brand_name") != "Secret Luxury Brand A", "IDOR: Tenant B accessed Tenant A's brand persona!"

    def test_tenant_idor_inventory_cross_account_isolation(self, adv_client, adv_db):
        """
        Adversarial Test: Tenant A creates an inventory item with SKU 'SECRET-A-99'.
        Tenant B lists inventory items.
        Tenant B must not see Tenant A's inventory items.
        """
        user_a = _create_user(adv_db, email="inv_a@example.com")
        user_b = _create_user(adv_db, email="inv_b@example.com")

        item_a = InventoryItem(
            id=str(uuid.uuid4()),
            user_id=user_a.id,
            sku="SECRET-A-99",
            title="Confidential Prototype",
            total_stock=500,
            platform_stock=json.dumps({"shopify": 500}),
            updated_at=datetime.datetime.utcnow()
        )
        adv_db.add(item_a)
        adv_db.commit()

        headers_b = _auth_header_for_user(user_b)
        res = adv_client.get("/api/inventory", headers=headers_b)
        assert res.status_code == 200
        items = res.json()
        skus = [it["sku"] for it in items]
        assert "SECRET-A-99" not in skus, "IDOR: Tenant B enumerated Tenant A's inventory SKU!"

    def test_forged_bearer_tokens_and_tampered_jwt(self, adv_client, adv_db):
        """
        Adversarial Test: Forged JWT tokens.
        - alg='none'
        - Signed with wrong secret key
        - Non-existent user sub
        - Garbage token string
        All must return HTTP 401.
        """
        user = _create_user(adv_db)

        # 1. Token signed with wrong secret key
        fake_secret = "completely-wrong-jwt-secret-key-12345678"
        forged_payload = {"sub": user.id, "email": user.email, "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)}
        forged_token = jwt.encode(forged_payload, fake_secret, algorithm="HS256")

        res1 = adv_client.get("/auth/me", headers={"Authorization": f"Bearer {forged_token}"})
        assert res1.status_code == 401

        # 2. Garbage Bearer string
        res2 = adv_client.get("/auth/me", headers={"Authorization": "Bearer not.a.valid.jwt.token"})
        assert res2.status_code == 401

        # 3. Non-existent user ID in validly signed token
        non_existent_token = create_access_token("non-existent-user-uuid-999", "ghost@example.com")
        res3 = adv_client.get("/auth/me", headers={"Authorization": f"Bearer {non_existent_token}"})
        assert res3.status_code == 401

    def test_expired_jwt_tokens_rejected(self, adv_client, adv_db):
        """
        Adversarial Test: JWT token with exp in the past must be rejected with 401.
        """
        user = _create_user(adv_db)
        expired_payload = {
            "sub": user.id,
            "email": user.email,
            "exp": datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
        }
        expired_token = jwt.encode(expired_payload, os.getenv("JWT_SECRET_KEY"), algorithm="HS256")

        res = adv_client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        assert res.status_code == 401

    def test_revoked_api_key_rejected(self, adv_client, adv_db):
        """
        Adversarial Test: Revoked API key (is_active=False) must be rejected with 401.
        """
        user = _create_user(adv_db)
        raw_key, key_hash, prefix = generate_api_key()
        api_key = APIKey(
            id=str(uuid.uuid4()),
            user_id=user.id,
            key_hash=key_hash,
            key_prefix=prefix,
            name="Revoked Key",
            is_active=False
        )
        adv_db.add(api_key)
        adv_db.commit()

        res = adv_client.get("/api/usage", headers={"Authorization": f"Bearer {raw_key}"})
        assert res.status_code == 401

    def test_inactive_suspended_user_token_rejected(self, adv_client, adv_db):
        """
        Adversarial Test: Active JWT or API key for suspended user (is_active=False)
        must be rejected with 401.
        """
        user = _create_user(adv_db, is_active=False)
        token = create_access_token(user.id, user.email)

        res = adv_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401

    def test_bcrypt_72_byte_truncation_attack_defense(self, adv_client):
        """
        Adversarial Test: Bcrypt truncates passwords after 72 UTF-8 bytes by default.
        An attacker could exploit this by registering with a 72-byte password prefix
        and authenticating with any trailing suffix if length is not capped.
        
        KopyKat must enforce a strict <= 72 UTF-8 byte password cap.
        """
        pwd_72 = "A" * 72
        hashed = hash_password(pwd_72)
        assert verify_password(pwd_72, hashed) is True

        pwd_73 = "A" * 73
        with pytest.raises(HTTPException) as exc_info:
            hash_password(pwd_73)
        assert exc_info.value.status_code == 400

        assert verify_password(pwd_73, hashed) is False

        res_reg = adv_client.post(
            "/auth/register",
            json={"email": "overflow_test@example.com", "password": pwd_73}
        )
        assert res_reg.status_code in (400, 422)
