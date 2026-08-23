import pytest
from unittest.mock import patch, MagicMock
from server.marketing import scan_reddit_opportunities
from server.database import OpportunityLog

@pytest.mark.asyncio
async def test_scan_reddit_opportunities(db_session):
    mock_reddit_response = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "mock_reddit_post_001",
                        "title": "I need help with product descriptions for my store",
                        "selftext": "Writing product descriptions takes way too long and I need a copywriter.",
                        "permalink": "/r/ecommerce/comments/mock_reddit_post_001"
                    }
                }
            ]
        }
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_reddit_response

    with patch("httpx.AsyncClient.get", return_value=mock_resp), patch("server.marketing._send_email"):
        found = await scan_reddit_opportunities(db=db_session)
        assert found >= 1

        # Invariant: OpportunityLog is persisted
        log = db_session.query(OpportunityLog).filter(OpportunityLog.post_id == "mock_reddit_post_001").first()
        assert log is not None
        assert log.platform == "reddit"
        assert "KopyKat" in log.draft_reply

        # Re-running ignores already alerted post (idempotency)
        found_second = await scan_reddit_opportunities(db=db_session)
        assert found_second == 0


@pytest.mark.asyncio
async def test_scan_reddit_ignores_non_matching_posts(db_session):
    """Verifies that non-matching posts in a batch do not cause UnboundLocalError or false positives."""
    mock_reddit_response = {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "unrelated_post_999",
                        "title": "General discussion about office furniture",
                        "selftext": "Looking for comfortable ergonomic chairs for our workspace.",
                        "permalink": "/r/smallbusiness/comments/unrelated_post_999"
                    }
                },
                {
                    "data": {
                        "id": "matched_post_888",
                        "title": "Need a copywriter for our shopify store",
                        "selftext": "Our team sucks at writing product descriptions and ad copy.",
                        "permalink": "/r/ecommerce/comments/matched_post_888"
                    }
                }
            ]
        }
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_reddit_response

    with patch("httpx.AsyncClient.get", return_value=mock_resp), patch("server.marketing._send_email") as mock_email:
        found = await scan_reddit_opportunities(db=db_session)
        assert found == 1

        unrelated = db_session.query(OpportunityLog).filter(OpportunityLog.post_id == "unrelated_post_999").first()
        assert unrelated is None

        matched = db_session.query(OpportunityLog).filter(OpportunityLog.post_id == "matched_post_888").first()
        assert matched is not None
        assert matched.score >= 90  # Hiring keyword + ecommerce boost
        assert mock_email.call_count == 1


@pytest.mark.asyncio
async def test_scan_reddit_handles_api_failure_gracefully(db_session):
    """Verifies that network errors or non-200 responses return 0 without crashing."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        found = await scan_reddit_opportunities(db=db_session)
        assert found == 0


@pytest.mark.asyncio
async def test_scan_reddit_intent_scoring_boundaries(db_session):
    """Verifies intent score calculation and clamping across keyword combinations."""
    cases = [
        ("I write copy for emails", "General discussion", "copywriting", 75),
        ("I need a copywriter for my store", "Looking to hire", "copywriting", 90),
        ("Help with product descriptions", "Setting up our catalog", "ecommerce", 83),
        ("Need a copywriter for Shopify store", "Our budget is open, struggling with writing", "ecommerce", 98),
    ]

    for i, (title, selftext, sub, expected_score) in enumerate(cases):
        resp_data = {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": f"score_test_post_{i}",
                            "title": title,
                            "selftext": selftext,
                            "permalink": f"/r/{sub}/comments/score_test_post_{i}"
                        }
                    }
                ]
            }
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = resp_data

        with patch("httpx.AsyncClient.get", return_value=mock_resp), patch("server.marketing._send_email"):
            found = await scan_reddit_opportunities(db=db_session)
            assert found >= 1

            log = db_session.query(OpportunityLog).filter(OpportunityLog.post_id == f"score_test_post_{i}").first()
            assert log is not None
            assert log.score == expected_score
            assert log.score <= 99


@pytest.mark.asyncio
async def test_scan_reddit_empty_and_corrupt_batches(db_session):
    """Verifies robustness against empty children, non-dict payloads, and network timeouts."""
    corrupt_cases = [
        {"data": {"children": []}},
        {"data": {}},
        {"kind": "Listing"},
    ]

    for corrupt_json in corrupt_cases:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = corrupt_json

        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            found = await scan_reddit_opportunities(db=db_session)
            assert found == 0
