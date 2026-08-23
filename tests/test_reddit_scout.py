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

    with patch("requests.get", return_value=mock_resp), patch("server.marketing._send_email"):
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
