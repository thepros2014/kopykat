import pytest

def test_security_headers_present(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("X-XSS-Protection") == "1; mode=block"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "geolocation=()" in response.headers.get("Permissions-Policy", "")

def test_cors_preflight_headers(client):
    response = client.options("/api/generate", headers={
        "Origin": "https://kopykat.onrender.com",
        "Access-Control-Request-Method": "POST"
    })
    assert response.status_code == 200
