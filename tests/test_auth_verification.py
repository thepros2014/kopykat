import pytest
import re
from datetime import datetime, timedelta
from server.database import User, VerificationToken

def test_request_email_verification(client, db_session, test_user):
    res = client.post("/auth/request-verification", json={"email": test_user.email})
    assert res.status_code == 200
    assert "verification link" in res.json()["message"]
    
    # Check token in DB
    vt = db_session.query(VerificationToken).filter(VerificationToken.user_id == test_user.id).first()
    assert vt is not None
    assert vt.token_type == "email_verification"

def test_verify_email_success(client, db_session, test_user):
    vt = VerificationToken(
        token="valid-test-verification-token-xyz12345",
        user_id=test_user.id,
        token_type="email_verification",
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )
    db_session.add(vt)
    db_session.commit()
    
    res = client.post("/auth/verify-email", json={"token": "valid-test-verification-token-xyz12345"})
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    
    # Verify user state updated
    user = db_session.query(User).filter(User.id == test_user.id).first()
    assert user.is_verified is True

def test_verify_email_expired_token(client, db_session, test_user):
    vt = VerificationToken(
        token="expired-token-abc987654321",
        user_id=test_user.id,
        token_type="email_verification",
        expires_at=datetime.utcnow() - timedelta(hours=1)
    )
    db_session.add(vt)
    db_session.commit()
    
    res = client.post("/auth/verify-email", json={"token": "expired-token-abc987654321"})
    assert res.status_code == 400
    assert "Invalid or expired" in res.json()["detail"]
