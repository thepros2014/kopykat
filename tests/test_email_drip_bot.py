import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from server.marketing import run_drip_campaigns
from server.database import User, DripLog

def test_run_drip_campaigns(db_session, test_user):
    # Set user created_at to 2 days ago (triggers Day 2 drip)
    test_user.created_at = datetime.utcnow() - timedelta(days=2)
    test_user.plan = "free"
    db_session.commit()

    with patch("server.marketing._send_email") as mock_send:
        sent = run_drip_campaigns(db=db_session)
        assert sent >= 1
        mock_send.assert_called_once()

        # Invariant: DripLog recorded to prevent duplicate sends
        log = db_session.query(DripLog).filter(DripLog.user_id == test_user.id, DripLog.step == 2).first()
        assert log is not None

        # Running again should send 0 emails (idempotent)
        sent_again = run_drip_campaigns(db=db_session)
        assert sent_again == 0
