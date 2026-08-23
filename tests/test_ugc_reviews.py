import pytest
from server.database import CustomerReview

def test_generate_post_purchase_drip(client, auth_headers):
    res = client.post(
        "/api/reviews/drip-templates",
        json={"product_name": "Leather Travel Duffel", "brand_tone": "Refined and luxurious", "incentive_offer": "20% off next order"},
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["product_name"] == "Leather Travel Duffel"
    assert len(data["drip_emails"]) == 3
    assert data["drip_emails"][0]["step"] == 1
    assert data["drip_emails"][1]["step"] == 2
    assert data["drip_emails"][2]["step"] == 3

def test_customer_review_sentiment_classification(client, auth_headers, test_user, db_session):
    # 1. Test Positive Review
    pos_res = client.post(
        "/api/reviews/submit",
        json={
            "customer_name": "Alice Johnson",
            "customer_email": "alice@example.com",
            "product_name": "Leather Travel Duffel",
            "rating": 5,
            "review_text": "I absolutely love this bag! High quality leather, fast shipping, and looks amazing."
        },
        headers=auth_headers
    )
    assert pos_res.status_code == 200
    pos_data = pos_res.json()
    assert pos_data["sentiment"] == "positive"
    assert pos_data["status"] == "published"

    # 2. Test Negative Review requiring action
    neg_res = client.post(
        "/api/reviews/submit",
        json={
            "customer_name": "Bob Smith",
            "customer_email": "bob@example.com",
            "product_name": "Leather Travel Duffel",
            "rating": 1,
            "review_text": "The zipper broke on day 2. Terrible quality and very disappointed with this purchase."
        },
        headers=auth_headers
    )
    assert neg_res.status_code == 200
    neg_data = neg_res.json()
    assert neg_data["sentiment"] == "negative"
    assert neg_data["status"] == "action_needed"
    assert "Dear Bob Smith" in neg_data["draft_reply"]

    # 3. List Reviews Feed
    list_res = client.get("/api/reviews", headers=auth_headers)
    assert list_res.status_code == 200
    reviews = list_res.json()
    assert len(reviews) >= 2


def test_customer_review_neutral_sentiment_classification(client, auth_headers):
    """Verifies that 3-star reviews are classified as neutral with action_needed status and feedback reply."""
    res = client.post(
        "/api/reviews/submit",
        json={
            "customer_name": "Charlie Davis",
            "customer_email": "charlie@example.com",
            "product_name": "Leather Travel Duffel",
            "rating": 3,
            "review_text": "The bag is decent and arrived on time, but the strap feels a bit stiff."
        },
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["sentiment"] == "neutral"
    assert data["status"] == "action_needed"
    assert "Charlie Davis" in data["draft_reply"]
    assert "improve" in data["draft_reply"] or "feedback" in data["draft_reply"]


def test_customer_review_negative_keyword_override(client, auth_headers):
    """Verifies that heavy negative text overrides a high star rating (e.g. sarcastic 5-star review)."""
    res = client.post(
        "/api/reviews/submit",
        json={
            "customer_name": "David Miller",
            "customer_email": "david@example.com",
            "product_name": "Leather Travel Duffel",
            "rating": 5,
            "review_text": "Terrible broken scam, awful quality, complete waste of money and never buy this."
        },
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["sentiment"] == "negative"
    assert data["status"] == "action_needed"
    assert "Dear David Miller" in data["draft_reply"]
    assert "refund" in data["draft_reply"].lower() or "replacement" in data["draft_reply"].lower()

