import re
from pathlib import Path
from unittest.mock import patch

import server.main as server_main
from server.auth import encrypt_credentials
from server.ai_credentials import get_active_ai_credentials, user_ai_credentials
from server.main import _csp_attribute_hashes, _validate_network_boundaries


BASE_DIR = Path(__file__).resolve().parents[1]


def test_html_pages_use_request_scoped_csp_and_local_admin_css(client):
    response = client.get("/admin")

    assert response.status_code == 200
    policy = response.headers["Content-Security-Policy"]
    assert re.search(r"script-src 'self' 'nonce-[^']+'", policy)
    assert "script-src 'self' 'unsafe-inline'" not in policy
    assert "https://cdn.tailwindcss.com" not in response.text
    assert "/static/admin.css" in response.text
    assert re.search(r"<script nonce=\"[^\"]+\">", response.text)


def test_legacy_browser_pages_do_not_touch_web_storage():
    for filename in ("frontend/index.html", "frontend/blog.html", "frontend/post.html", "frontend/dashboard.html"):
        content = (BASE_DIR / filename).read_text(encoding="utf-8")
        assert "localStorage" not in content
        assert "sessionStorage" not in content


def test_service_worker_only_caches_static_assets():
    worker = (BASE_DIR / "frontend/sw.js").read_text(encoding="utf-8")

    assert "kopykat-static-v2" in worker
    assert "requestUrl.pathname.startsWith('/static/')" in worker
    assert "event.request.destination" in worker
    assert "'/dashboard'" not in worker
    assert "event.request.url.includes('/api/')" not in worker


def test_csp_hashes_are_deterministic_and_network_boundaries_fail_closed():
    hashes = _csp_attribute_hashes('<button onclick="doThing()">Go</button>', re.compile(r"\bonclick\s*=\s*(?P<quote>[\"'])(?P<value>.*?)(?P=quote)"))
    assert len(hashes) == 1
    assert all(len(value) == 44 for value in hashes)

    try:
        _validate_network_boundaries(["http://example.test"], ["example.test"])
    except RuntimeError as exc:
        assert "ALLOWED_ORIGINS" in str(exc)
    else:
        raise AssertionError("insecure strict origin was accepted")


def test_byok_uses_separate_bounded_server_activity_and_refunds(client, db_session, test_user, auth_headers, monkeypatch):
    test_user.plan = "megastore"
    test_user.generations = 0
    test_user.monthly_generations = 0
    test_user.purchased_generations = 0
    test_user.custom_ai_provider = "openai"
    test_user.custom_ai_key_encrypted = encrypt_credentials("sk-customer-key-123456")
    db_session.commit()
    monkeypatch.setattr(server_main, "BYOK_SERVER_ACTIVITY_LIMIT", 2)

    result = {
        "variations": ["draft"],
        "generations_used": 1,
        "generation_time_ms": 1,
    }
    with patch("server.main.generate_copy", return_value=result):
        first = client.post(
            "/api/generate",
            headers=auth_headers,
            json={"type": "product_description", "context": "A durable travel mug"},
        )
        second = client.post(
            "/api/generate",
            headers=auth_headers,
            json={"type": "product_description", "context": "A durable travel mug"},
        )
        blocked = client.post(
            "/api/generate",
            headers=auth_headers,
            json={"type": "product_description", "context": "A durable travel mug"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert blocked.status_code == 429
    db_session.refresh(test_user)
    assert test_user.generations == 0
    assert test_user.byok_activity_used == 2

    with user_ai_credentials(test_user):
        active = get_active_ai_credentials()
        assert active is not None
        assert active.provider == "openai"
        assert active.api_key == "sk-customer-key-123456"
    assert get_active_ai_credentials() is None


def test_byok_failed_generation_refunds_server_activity(client, db_session, test_user, auth_headers, monkeypatch):
    test_user.plan = "megastore"
    test_user.generations = 0
    test_user.monthly_generations = 0
    test_user.purchased_generations = 0
    test_user.custom_ai_provider = "gemini"
    test_user.custom_ai_key_encrypted = encrypt_credentials("AIza-customer-key-123456")
    db_session.commit()
    monkeypatch.setattr(server_main, "BYOK_SERVER_ACTIVITY_LIMIT", 5)

    with patch("server.main.generate_copy", side_effect=RuntimeError("provider unavailable")):
        response = client.post(
            "/api/generate",
            headers=auth_headers,
            json={"type": "product_description", "context": "A durable travel mug"},
        )

    assert response.status_code == 500
    db_session.refresh(test_user)
    assert test_user.byok_activity_used == 0
    assert test_user.generations == 0


def test_self_hosted_license_catalog_is_separate_from_managed_checkout(client):
    response = client.get("/api/plans")

    assert response.status_code == 200
    licenses = response.json()["self_hosted_licenses"]
    assert licenses["pro"]["price_usd"] == 7500
    assert licenses["business"]["price_usd"] == 15000
    assert licenses["enterprise"]["price_usd"] == 30000
    assert licenses["white_label"]["price_usd"] == 50000
    assert all(item["billing_type"] == "annual_license" for item in licenses.values())
    assert response.json()["self_hosted_deployment"]["price_usd"] == 12000
    assert response.json()["self_hosted_deployment"]["per_user"] is False
