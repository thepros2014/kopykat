"""
test_empirical_inventory.py
Challenger 2 Empirical Verification Test Harness for Milestone 2.
Tests loop-free fanout, idempotency ledger, concurrent race conditions,
drift reconciliation, zero-floor clamping, and edge cases.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import unittest
import uuid
from datetime import datetime

# Configure test environment
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-32-chars-long-strictly-set"
os.environ["INTEGRATION_ENCRYPTION_KEY"] = "wB2tN4a-7iL3sZ_qU8rX0vY5mP1oJ9eK6cF_dG4hA8s="
os.environ["ENVIRONMENT"] = "testing"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from server.database import Base, InventoryItem, InventorySyncLog, InventoryWebhookEvent, User, UserIntegration
from server.inventory import (
    PLATFORM_ALIASES,
    SUPPORTED_INVENTORY_PLATFORMS,
    normalize_platform_name,
    reconcile_inventory_sku,
    sync_inventory_across_platforms,
)


class EmpiricalInventoryTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use StaticPool with in-memory SQLite for multi-threaded testing
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)

    def setUp(self):
        self.db = self.SessionLocal()
        self.user_id = f"user-{uuid.uuid4()}"
        self.user = User(
            id=self.user_id,
            email=f"{self.user_id}@example.com",
            hashed_password="hash",
            full_name="Tester",
            plan="boutique",
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _setup_all_platforms(self, user_id: str):
        for p in SUPPORTED_INVENTORY_PLATFORMS:
            integ = UserIntegration(
                id=f"integ-{user_id}-{p}",
                user_id=user_id,
                platform=p,
                credentials="{}",
                status="connected",
            )
            self.db.add(integ)
        self.db.commit()

    # --- 1. LOOP-FREE FANOUT ACROSS ALL 8 PLATFORMS ---
    def test_loop_free_fanout_all_platforms_individually(self):
        """Verify that triggering from platform X fans out to all 7 other platforms and omits X."""
        all_8 = {"shopify", "amazon", "etsy", "tiktok", "ebay", "walmart", "temu", "woocommerce"}
        self.assertEqual(SUPPORTED_INVENTORY_PLATFORMS, all_8)

        for trigger_p in all_8:
            user_id = f"u-{trigger_p}-{uuid.uuid4()}"
            user = User(id=user_id, email=f"{user_id}@test.com", hashed_password="h", plan="boutique")
            self.db.add(user)
            self.db.commit()
            self._setup_all_platforms(user_id)

            sku = f"SKU-{trigger_p.upper()}-100"
            res = sync_inventory_across_platforms(
                user_id=user_id,
                sku=sku,
                delta=50,
                trigger_platform=trigger_p,
                db=self.db,
                event_id=f"evt-{trigger_p}-initial",
                title=f"Item {trigger_p}",
            )

            # Assert trigger platform is source_event
            self.assertEqual(res["trigger_platform"], trigger_p)
            self.assertEqual(res["new_stock"], 50)
            self.assertEqual(res["fanout_results"][trigger_p], "source_event")

            # Assert all other 7 platforms got synced_to_50
            other_platforms = all_8 - {trigger_p}
            for other_p in other_platforms:
                self.assertIn(other_p, res["fanout_results"])
                self.assertEqual(res["fanout_results"][other_p], "synced_to_50")

            # Verify item DB record
            item = self.db.query(InventoryItem).filter(InventoryItem.user_id == user_id, InventoryItem.sku == sku).first()
            self.assertIsNotNone(item)
            self.assertEqual(item.total_stock, 50)
            p_stock = json.loads(item.platform_stock)
            self.assertEqual(p_stock[trigger_p], 50)
            for other_p in other_platforms:
                self.assertEqual(p_stock[other_p], 50)

            # Verify sync log DB record
            log = self.db.query(InventorySyncLog).filter(InventorySyncLog.user_id == user_id, InventorySyncLog.sku == sku).first()
            self.assertIsNotNone(log)
            self.assertEqual(log.trigger_platform, trigger_p)
            self.assertEqual(log.quantity_change, 50)
            self.assertEqual(log.new_quantity, 50)
            log_fanout = json.loads(log.fanout_results)
            self.assertEqual(log_fanout[trigger_p], "source_event")
            for other_p in other_platforms:
                self.assertEqual(log_fanout[other_p], "synced_to_50")

    def test_fanout_with_platform_alias_and_casing(self):
        """Verify alias normalization (e.g. tiktok_shop -> tiktok, woo -> woocommerce, UPPERCASE)."""
        self._setup_all_platforms(self.user_id)
        sku = "ALIAS-TEST-SKU"

        # Trigger with "TIKTOK_SHOP"
        res1 = sync_inventory_across_platforms(
            user_id=self.user_id,
            sku=sku,
            delta=30,
            trigger_platform="TIKTOK_SHOP",
            db=self.db,
            event_id="evt-alias-1",
        )
        self.assertEqual(res1["trigger_platform"], "tiktok")
        self.assertEqual(res1["fanout_results"]["tiktok"], "source_event")
        self.assertEqual(res1["fanout_results"]["shopify"], "synced_to_30")

        # Trigger with "woo"
        res2 = sync_inventory_across_platforms(
            user_id=self.user_id,
            sku=sku,
            delta=-5,
            trigger_platform="woo",
            db=self.db,
            event_id="evt-alias-2",
        )
        self.assertEqual(res2["trigger_platform"], "woocommerce")
        self.assertEqual(res2["fanout_results"]["woocommerce"], "source_event")
        self.assertEqual(res2["fanout_results"]["tiktok"], "synced_to_25")
        self.assertEqual(res2["new_stock"], 25)

    def test_disconnected_integrations_ignored(self):
        """Verify integrations with status != 'connected' are omitted from fanout."""
        integ_active = UserIntegration(
            id=f"integ-act-{uuid.uuid4()}",
            user_id=self.user_id,
            platform="shopify",
            credentials="{}",
            status="connected",
        )
        integ_paused = UserIntegration(
            id=f"integ-pau-{uuid.uuid4()}",
            user_id=self.user_id,
            platform="ebay",
            credentials="{}",
            status="disconnected",
        )
        self.db.add_all([integ_active, integ_paused])
        self.db.commit()

        res = sync_inventory_across_platforms(
            user_id=self.user_id,
            sku="DISCONN-SKU",
            delta=10,
            trigger_platform="amazon",
            db=self.db,
            event_id="evt-disc-1",
        )
        self.assertIn("shopify", res["fanout_results"])
        self.assertNotIn("ebay", res["fanout_results"])

    # --- 2. WEBHOOK IDEMPOTENCY LEDGER ---
    def test_webhook_idempotency_sequential_replay(self):
        """Replaying identical (platform, event_id) must be deduplicated and not mutate stock."""
        self._setup_all_platforms(self.user_id)
        sku = "IDEMP-SEQ-SKU"

        # Initial seed
        res0 = sync_inventory_across_platforms(
            user_id=self.user_id,
            sku=sku,
            delta=100,
            trigger_platform="shopify",
            db=self.db,
            event_id="evt-seed-100",
        )
        self.assertEqual(res0["new_stock"], 100)

        # First delivery of order event: -10
        res1 = sync_inventory_across_platforms(
            user_id=self.user_id,
            sku=sku,
            delta=-10,
            trigger_platform="shopify",
            db=self.db,
            event_id="order-shopify-9999",
        )
        self.assertEqual(res1["new_stock"], 90)
        self.assertEqual(res1["previous_stock"], 100)

        # Replay the identical event 10 times
        for i in range(10):
            replay_res = sync_inventory_across_platforms(
                user_id=self.user_id,
                sku=sku,
                delta=-10,
                trigger_platform="shopify",
                db=self.db,
                event_id="order-shopify-9999",
            )
            self.assertEqual(replay_res["status"], "already_processed")
            self.assertEqual(replay_res["event_id"], "order-shopify-9999")

        # Verify stock remains 90, NOT 0 or negative
        item = self.db.query(InventoryItem).filter(InventoryItem.user_id == self.user_id, InventoryItem.sku == sku).first()
        self.assertEqual(item.total_stock, 90)

    def test_idempotency_composite_key_platform_differentiation(self):
        """Same event_id from two different platforms should both process (composite platform+event_id)."""
        sku = "COMPOSITE-IDEMP-SKU"
        res_shopify = sync_inventory_across_platforms(
            user_id=self.user_id,
            sku=sku,
            delta=50,
            trigger_platform="shopify",
            db=self.db,
            event_id="event-12345",
        )
        self.assertEqual(res_shopify["new_stock"], 50)

        res_amazon = sync_inventory_across_platforms(
            user_id=self.user_id,
            sku=sku,
            delta=-5,
            trigger_platform="amazon",
            db=self.db,
            event_id="event-12345",  # same event_id, different platform
        )
        self.assertEqual(res_amazon["new_stock"], 45)

        # But replay of res_amazon is blocked
        res_amazon_dup = sync_inventory_across_platforms(
            user_id=self.user_id,
            sku=sku,
            delta=-5,
            trigger_platform="amazon",
            db=self.db,
            event_id="event-12345",
        )
        self.assertEqual(res_amazon_dup["status"], "already_processed")

    # --- 3. CONCURRENT WEBHOOK DELIVERIES (RACE CONDITIONS) ---
    def test_concurrent_identical_webhook_deliveries(self):
        """Simulate 20 concurrent threads delivering the exact same webhook event."""
        sku = "CONCURRENT-IDEMP-SKU"
        event_id = f"concurrent-evt-{uuid.uuid4()}"

        # Create initial item with stock 100
        init_res = sync_inventory_across_platforms(
            user_id=self.user_id,
            sku=sku,
            delta=100,
            trigger_platform="shopify",
            db=self.db,
            event_id=f"init-{uuid.uuid4()}",
        )
        self.assertEqual(init_res["new_stock"], 100)

        def worker_task():
            session = self.SessionLocal()
            try:
                result = sync_inventory_across_platforms(
                    user_id=self.user_id,
                    sku=sku,
                    delta=-10,
                    trigger_platform="shopify",
                    db=session,
                    event_id=event_id,
                )
                return result
            finally:
                session.close()

        num_threads = 20
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker_task) for _ in range(num_threads)]
            results = [f.result() for f in futures]

        processed_count = sum(1 for r in results if r.get("status") != "already_processed" and "new_stock" in r)
        dedup_count = sum(1 for r in results if r.get("status") == "already_processed")

        self.assertEqual(processed_count, 1, f"Expected exactly 1 processed request, got {processed_count}")
        self.assertEqual(dedup_count, num_threads - 1, f"Expected {num_threads - 1} duplicates, got {dedup_count}")

        # Verify stock in DB decreased by exactly 10 (from 100 to 90)
        self.db.expire_all()
        item = self.db.query(InventoryItem).filter(InventoryItem.user_id == self.user_id, InventoryItem.sku == sku).first()
        self.assertEqual(item.total_stock, 90)

    # --- 4. DRIFT RECONCILIATION ---
    def test_drift_reconciliation_calculations_and_fanout(self):
        """Test drift reconciliation with positive, negative, and zero drift."""
        self._setup_all_platforms(self.user_id)
        sku = "DRIFT-RECON-SKU"

        # Seed initial stock = 50
        sync_inventory_across_platforms(
            user_id=self.user_id,
            sku=sku,
            delta=50,
            trigger_platform="shopify",
            db=self.db,
            event_id="drift-seed-1",
        )

        # 1. Audit found 42 units (drift = 42 - 50 = -8)
        recon1 = reconcile_inventory_sku(
            user_id=self.user_id,
            sku=sku,
            canonical_stock=42,
            db=self.db,
        )
        self.assertEqual(recon1["previous_stock"], 50)
        self.assertEqual(recon1["reconciled_stock"], 42)
        self.assertEqual(recon1["drift_corrected"], -8)
        for p in SUPPORTED_INVENTORY_PLATFORMS:
            self.assertEqual(recon1["fanout_results"][p], "reconciled_to_42")

        # 2. Audit found 60 units (drift = 60 - 42 = +18)
        recon2 = reconcile_inventory_sku(
            user_id=self.user_id,
            sku=sku,
            canonical_stock=60,
            db=self.db,
        )
        self.assertEqual(recon2["previous_stock"], 42)
        self.assertEqual(recon2["reconciled_stock"], 60)
        self.assertEqual(recon2["drift_corrected"], 18)

        # 3. Audit found 60 units again (drift = 0)
        recon3 = reconcile_inventory_sku(
            user_id=self.user_id,
            sku=sku,
            canonical_stock=60,
            db=self.db,
        )
        self.assertEqual(recon3["previous_stock"], 60)
        self.assertEqual(recon3["reconciled_stock"], 60)
        self.assertEqual(recon3["drift_corrected"], 0)

        # Verify audit logs in DB
        logs = self.db.query(InventorySyncLog).filter(
            InventorySyncLog.user_id == self.user_id,
            InventorySyncLog.sku == sku,
            InventorySyncLog.trigger_platform == "reconciliation_engine",
        ).all()
        self.assertEqual(len(logs), 3)

    def test_drift_reconciliation_creates_item_if_missing(self):
        """Reconciliation of an unlisted SKU should create the item with canonical stock."""
        sku = "NEW-UNSEEN-SKU"
        recon = reconcile_inventory_sku(
            user_id=self.user_id,
            sku=sku,
            canonical_stock=25,
            db=self.db,
        )
        self.assertEqual(recon["reconciled_stock"], 25)
        self.assertEqual(recon["previous_stock"], 0)
        self.assertEqual(recon["drift_corrected"], 25)

        item = self.db.query(InventoryItem).filter(InventoryItem.user_id == self.user_id, InventoryItem.sku == sku).first()
        self.assertIsNotNone(item)
        self.assertEqual(item.total_stock, 25)

    # --- 5. ZERO-FLOOR CLAMPING BEHAVIOR ---
    def test_zero_floor_clamping_new_item_negative_delta(self):
        """A new item created with a negative delta must clamp initial stock to 0."""
        sku = "NEW-NEG-SKU"
        res = sync_inventory_across_platforms(
            user_id=self.user_id,
            sku=sku,
            delta=-20,
            trigger_platform="amazon",
            db=self.db,
            event_id="evt-neg-1",
        )
        self.assertEqual(res["new_stock"], 0)
        item = self.db.query(InventoryItem).filter(InventoryItem.user_id == self.user_id, InventoryItem.sku == sku).first()
        self.assertEqual(item.total_stock, 0)

    def test_zero_floor_clamping_oversell(self):
        """Overselling an existing item (e.g. stock=5, delta=-100) must clamp to 0."""
        sku = "OVERSELL-SKU"
        sync_inventory_across_platforms(
            user_id=self.user_id,
            sku=sku,
            delta=5,
            trigger_platform="amazon",
            db=self.db,
            event_id="evt-seed-5",
        )
        res = sync_inventory_across_platforms(
            user_id=self.user_id,
            sku=sku,
            delta=-100,
            trigger_platform="amazon",
            db=self.db,
            event_id="evt-oversell-1",
        )
        self.assertEqual(res["previous_stock"], 5)
        self.assertEqual(res["new_stock"], 0)
        item = self.db.query(InventoryItem).filter(InventoryItem.user_id == self.user_id, InventoryItem.sku == sku).first()
        self.assertEqual(item.total_stock, 0)

    # --- 6. EDGE CASES ---
    def test_sku_casing_and_whitespace_insensitivity(self):
        """Ensure 'sku-123', 'SKU-123', and '  SKU-123  ' resolve to the same record."""
        sync_inventory_across_platforms(
            user_id=self.user_id,
            sku="sku-uniform-1",
            delta=50,
            trigger_platform="shopify",
            db=self.db,
            event_id="evt-case-1",
        )
        # Update using uppercase and whitespace
        res = sync_inventory_across_platforms(
            user_id=self.user_id,
            sku="  SKU-UNIFORM-1  ",
            delta=-5,
            trigger_platform="shopify",
            db=self.db,
            event_id="evt-case-2",
        )
        self.assertEqual(res["previous_stock"], 50)
        self.assertEqual(res["new_stock"], 45)


def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(EmpiricalInventoryTestSuite)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
