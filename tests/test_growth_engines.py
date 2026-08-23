import pytest
from unittest.mock import patch
from server.database import User, BlogPost, OpportunityLog, DripLog, Subscription, RevenueRecord

def test_seo_analytics_endpoint(client, auth_headers, db_session):
    # Seed a published blog post
    post = BlogPost(
        id="test_post_analytics_001",
        title="10 Ways to Scale E-Commerce Dropshipping with AI",
        slug="scale-dropshipping-with-ai",
        keyword="scale dropshipping",
        meta_desc="Learn how to scale your store.",
        content="<p>SEO content here...</p>",
        word_count=500,
        published=True
    )
    db_session.add(post)
    db_session.commit()

    res = client.get("/api/seo/analytics", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_posts"] >= 1
    assert data["total_words_generated"] >= 500
    assert "/sitemap.xml" in data["sitemap_url"]
    assert data["indexing_status"] == "active"
    assert len(data["recent_articles"]) >= 1

def test_seo_ping_index_endpoint(client, auth_headers):
    res = client.post("/api/seo/ping-index", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "/sitemap.xml" in data["sitemap_url"]
    assert len(data["pings"]) >= 1

def test_drip_analytics_endpoint(client, auth_headers, db_session, test_user):
    # Seed a DripLog
    drip = DripLog(
        id="drip_log_001",
        user_id=test_user.id,
        step=2
    )
    db_session.add(drip)
    db_session.commit()

    res = client.get("/api/drip/analytics", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "funnel" in data
    assert data["funnel"]["day2_value_drips_sent"] >= 1
    assert data["status"] == "autonomous_active"

def test_opportunity_leads_with_score(client, auth_headers, db_session):
    # Seed OpportunityLog with score
    log = OpportunityLog(
        id="opp_scored_001",
        platform="reddit",
        post_id="post_scored_123",
        post_title="Looking to hire a copywriter for product descriptions",
        post_url="https://reddit.com/r/ecommerce/comments/123",
        draft_reply="I recommend KopyKat to automate product copy.",
        score=98,
        alerted=True
    )
    db_session.add(log)
    db_session.commit()

    res = client.get("/api/leads", headers=auth_headers)
    assert res.status_code == 200
    leads = res.json()
    assert len(leads) >= 1
    target = next((l for l in leads if l["id"] == "opp_scored_001"), None)
    assert target is not None
    assert target["score"] == 98

def test_admin_mrr_metrics_endpoint(client, db_session, test_user):
    # Seed a subscription and revenue record
    sub = Subscription(
        id="sub_mrr_test",
        user_id=test_user.id,
        stripe_subscription_id="sub_stripe_123",
        plan="standard",
        status="active"
    )
    rev = RevenueRecord(
        id="rev_mrr_test",
        stripe_payment_id="pay_stripe_123",
        user_id=test_user.id,
        amount_cents=37949,
        plan="standard",
        type="subscription",
        status="succeeded"
    )
    db_session.add(sub)
    db_session.add(rev)
    db_session.commit()

    with patch("server.main.ADMIN_SECRET", "test_admin_secret_key"):
        # Without secret header -> 403
        res_fail = client.get("/admin/mrr-metrics")
        assert res_fail.status_code == 403

        # With secret header -> 200
        res_ok = client.get("/admin/mrr-metrics", headers={"X-Admin-Secret": "test_admin_secret_key"})
        assert res_ok.status_code == 200
        data = res_ok.json()
        assert data["mrr_usd"] >= 379.49
        assert data["arr_usd"] >= 4553.88
        assert data["active_subscribers"] >= 1
        assert data["software_asset_score"] == 9.2
        assert "$120,000" in data["valuation_estimate_usd"]["asset_sale_range"]


def test_admin_mrr_metrics_multi_tier_and_churn_tracking(client, db_session):
    """Verifies multi-tier MRR summation, active tier counts, and subscriber churn percentage."""
    import uuid

    # Create users and subscriptions
    users_data = [
        ("u_boutique_active", "boutique", "active"),
        ("u_standard_active", "standard", "active"),
        ("u_megastore_active", "megastore", "active"),
        ("u_boutique_canceled", "boutique", "canceled"),
        ("u_standard_pastdue", "standard", "past_due"),
    ]

    for uid, plan, status in users_data:
        user = User(
            id=uid,
            email=f"{uid}@example.com",
            hashed_password="hashed_dummy_password",
            plan=plan,
            generations=10,
            monthly_limit=250,
            is_active=True
        )
        sub = Subscription(
            id=f"sub_{uid}",
            user_id=uid,
            stripe_subscription_id=f"stripe_sub_{uid}",
            plan=plan,
            status=status
        )
        db_session.add(user)
        db_session.add(sub)

    db_session.commit()

    with patch("server.main.ADMIN_SECRET", "test_admin_secret_key"):
        res = client.get("/admin/mrr-metrics", headers={"X-Admin-Secret": "test_admin_secret_key"})
        assert res.status_code == 200
        data = res.json()

        assert data["active_subscribers"] == 3
        assert data["canceled_subscribers"] == 1
        assert data["past_due_subscribers"] == 1
        assert data["active_subscribers_by_tier"]["boutique"] == 1
        assert data["active_subscribers_by_tier"]["standard"] == 1
        assert data["active_subscribers_by_tier"]["megastore"] == 1
        assert data["mrr_usd"] == 10198.61
        assert data["arr_usd"] == 122383.32
        assert data["churn_rate_pct"] == 25.0
        assert data["pricing_model"]["boutique_usd_mo"] == 179.49
        assert data["pricing_model"]["standard_usd_mo"] == 379.49
        assert data["pricing_model"]["megastore_usd_mo"] == 9639.63

