import pytest
from server.database import User, BlogPost, OpportunityLog, DripLog

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
