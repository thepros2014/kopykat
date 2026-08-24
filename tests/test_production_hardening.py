import json
from unittest.mock import patch

import pytest

from server.connector_engine import SSRFError, SafeSyncHTTPClient
from server.connector_registry import execute_operation
from server.main import _sanitize_campaign_assets
from server.shopify_import import normalize_shopify_domain


def test_ready_probe_and_request_id_are_operational(client):
    response = client.get("/ready", headers={"X-Request-ID": "release-check-01"})

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.headers["X-Request-ID"] == "release-check-01"


def test_trusted_host_rejects_unlisted_host(client):
    response = client.get("/health", headers={"Host": "attacker.example"})

    assert response.status_code == 400


def test_auth_version_revokes_existing_jwt(client, db_session, test_user, auth_headers):
    assert client.get("/auth/me", headers=auth_headers).status_code == 200

    test_user.auth_version += 1
    db_session.commit()

    response = client.get("/auth/me", headers=auth_headers)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "value",
    [
        "http://store.myshopify.com",
        "https://evil.example/store.myshopify.com",
        "https://user:pass@store.myshopify.com",
        "https://store.myshopify.com/admin",
        "https://store.myshopify.com:443",
    ],
)
def test_shopify_import_accepts_only_canonical_store_hosts(value):
    with pytest.raises(ValueError):
        normalize_shopify_domain(value)


def test_shopify_import_canonicalizes_store_name():
    assert normalize_shopify_domain("https://demo-store.myshopify.com/") == "demo-store.myshopify.com"
    assert normalize_shopify_domain("demo-store") == "demo-store.myshopify.com"


def test_sync_connector_execution_uses_bounded_safe_response_parser():
    class FakeResponse:
        status_code = 200
        content = b'{"ok": true}'
        text = content.decode()

        def json(self):
            return json.loads(self.content)

    class FakeSafeClient:
        called = None

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def request(self, method, url, **kwargs):
            FakeSafeClient.called = (method, url, kwargs)
            return FakeResponse()

    spec = {
        "version": 1,
        "status": "active",
        "base_url": "https://api.example.com",
        "operations": [{"name": "health", "method": "GET", "path": "/health"}],
    }
    with patch("server.connector_registry.SafeSyncHTTPClient", FakeSafeClient), patch(
        "server.connector_registry.validate_public_url", side_effect=lambda value, *args, **kwargs: value
    ):
        result = execute_operation(spec, "health")

    assert result == {"status_code": 200, "data": {"ok": True}}
    assert FakeSafeClient.called[0] == "GET"
    assert FakeSafeClient.called[1] == "https://api.example.com/health"


def test_sync_safe_client_blocks_private_destinations_before_connecting():
    with SafeSyncHTTPClient() as client:
        with pytest.raises(SSRFError):
            client.get("https://127.0.0.1/internal")


def test_ai_campaign_assets_are_sanitized_before_storage_or_rendering():
    assets = _sanitize_campaign_assets({
        "blog_post": {
            "title": "<img src=x onerror=alert(1)>Launch",
            "content": '<script>alert(1)</script><p>Safe <a href="javascript:bad()">copy</a></p>',
        },
        "email_drip": [{"subject": "<b>Subject</b>", "body": "<iframe src=x></iframe><p>Body</p>"}],
        "social_posts": ["<script>bad()</script>Post"],
    })

    assert assets["blog_post"]["title"] == "Launch"
    assert "script" not in assets["blog_post"]["content"]
    assert "javascript:" not in assets["blog_post"]["content"]
    assert "iframe" not in assets["email_drip"][0]["body"]
    assert assets["social_posts"] == ["bad()Post"]
