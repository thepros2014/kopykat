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
