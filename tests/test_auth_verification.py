import pytest
import hashlib
from datetime import datetime, timedelta
from server.database import User, VerificationToken

def test_request_email_verification(client, db_session, test_user):
    res = client.post("/auth/request-verification", json={"email": test_user.email})
    assert res.status_code == 200
    assert "verification link" in res.json()["message"]
    
    # Check hashed token in DB
    vt = db_session.query(VerificationToken).filter(VerificationToken.user_id == test_user.id).first()
    assert vt is not None
    assert vt.token_type == "email_verification"
    assert len(vt.token) == 64  # SHA-256 hex digest length

def test_verify_email_success(client, db_session, test_user):
    raw_token = "valid-test-verification-token-xyz12345"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    vt = VerificationToken(
        token=token_hash,
        user_id=test_user.id,
        token_type="email_verification",
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )
    db_session.add(vt)
    db_session.commit()
    
    res = client.post("/auth/verify-email", json={"token": raw_token})
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    
    # Verify user state updated
    user = db_session.query(User).filter(User.id == test_user.id).first()
    assert user.is_verified is True

def test_verify_email_expired_token(client, db_session, test_user):
    raw_token = "expired-token-abc987654321"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    vt = VerificationToken(
        token=token_hash,
        user_id=test_user.id,
        token_type="email_verification",
        expires_at=datetime.utcnow() - timedelta(hours=1)
    )
    db_session.add(vt)
    db_session.commit()
    
    res = client.post("/auth/verify-email", json={"token": raw_token})
    assert res.status_code == 400
    assert "Invalid or expired" in res.json()["detail"]

def test_password_reset_flow(client, db_session, test_user):
    raw_token = "pwd-reset-test-token-777888"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    vt = VerificationToken(
        token=token_hash,
        user_id=test_user.id,
        token_type="password_reset",
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )
    db_session.add(vt)
    db_session.commit()

    # Submit new password
    res = client.post("/auth/reset-password", json={
        "token": raw_token,
        "new_password": "SuperSecureNewPassword123!"
    })
    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # Verify user can log in with new password
    login_res = client.post("/auth/login", json={
        "email": test_user.email,
        "password": "SuperSecureNewPassword123!"
    })
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()
