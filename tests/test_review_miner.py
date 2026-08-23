import pytest
from server.database import User, CompetitorAudit

def test_mine_competitor_reviews_endpoint(client, db_session, test_user, auth_headers, monkeypatch):
    mock_mined_data = {
        "extracted_flaws": [
            "Zipper breaks on day 2",
            "Shoulder straps have zero padding",
            "Not truly waterproof in heavy rain"
        ],
        "counter_description": "Engineered with reinforced YKK waterproof zippers and ergonomic memory-foam shoulder straps that never snap.",
        "comparison_points": [
            {
                "aspect": "Zippers",
                "competitor_flaw": "Fragile plastic teeth that jam",
                "our_advantage": "Military-grade YKK metal zippers"
            }
        ],
        "ad_hooks": [
            "Tired of travel backpacks with broken zippers? Here is why ours has a lifetime guarantee."
        ]
    }

    async def mock_mine(product_name, competitor_name, reviews_text):
        return mock_mined_data

    monkeypatch.setattr("server.ai_engine.mine_competitor_reviews", mock_mine)

    initial_gens = test_user.generations

    res = client.post(
        "/api/competitor/mine-reviews",
        json={
            "product_name": "UltraShield Backpack",
            "competitor_name": "GenericBag",
            "reviews_text": "This backpack broke on day 2! The zipper completely came off the track."
        },
        headers=auth_headers
    )

    assert res.status_code == 200
    data = res.json()
    assert data["product_name"] == "UltraShield Backpack"
    assert len(data["extracted_flaws"]) == 3
    assert "YKK" in data["counter_description"]

    # Invariant: 1 credit deducted atomically
    db_session.expire_all()
    user = db_session.query(User).filter(User.id == test_user.id).first()
    assert user.generations == initial_gens - 1

    # Invariant: Audit record created in DB
    audit = db_session.query(CompetitorAudit).filter(CompetitorAudit.id == data["id"]).first()
    assert audit is not None
    assert audit.product_name == "UltraShield Backpack"
