import pytest
from server.connector_engine import validate_public_url, ConnectorError, build_connector_spec
from server.connector_registry import validate_connector_spec

def test_validate_public_url_blocks_localhost():
    with pytest.raises(ConnectorError, match="Local connector URLs are not permitted"):
        validate_public_url("https://localhost/api/spec.json")

def test_validate_public_url_blocks_http_scheme():
    with pytest.raises(ConnectorError, match="requires an HTTPS URL"):
        validate_public_url("http://api.example.com/spec.json")

def test_validate_public_url_blocks_private_ips():
    with pytest.raises(ConnectorError):
        validate_public_url("https://127.0.0.1:8000/openapi.json")

def test_build_connector_spec_valid(monkeypatch):
    # Mock DNS lookup to return a public IP for testing
    monkeypatch.setattr("socket.getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))])
    
    sample_doc = {
        "openapi": "3.0.0",
        "info": {"title": "Test Marketplace API", "version": "1.0.0"},
        "servers": [{"url": "https://api.testmarketplace.com/v1"}],
        "paths": {
            "/products": {
                "get": {
                    "operationId": "listProducts",
                    "summary": "List all products"
                },
                "post": {
                    "operationId": "createProduct",
                    "summary": "Create a new product"
                }
            }
        },
        "components": {
            "securitySchemes": {
                "BearerAuth": {"type": "http", "scheme": "bearer"}
            }
        }
    }
    
    spec = build_connector_spec(sample_doc, "https://api.testmarketplace.com/openapi.json")
    assert spec["platform_name"] == "Test Marketplace API"
    assert spec["base_url"] == "https://api.testmarketplace.com/v1"
    assert len(spec["operations"]) == 2
    assert "bearer" in spec["authentication_modes"]
    assert spec["status"] == "draft"
    
    # Verify specification passes restricted runtime validation
    validated = validate_connector_spec(spec)
    assert validated["version"] == 1
    assert len(validated["operations"]) == 2

def test_connector_discovery_api_endpoint(client, auth_headers, monkeypatch):
    sample_spec = {
        "version": 1,
        "platform_name": "Acme Commerce API",
        "source_url": "https://api.acme.com/openapi.json",
        "base_url": "https://api.acme.com/v1",
        "authentication_modes": ["api_key"],
        "operations": [{"name": "createProduct", "method": "POST", "path": "/products", "summary": "Add item"}],
        "status": "draft"
    }
    
    monkeypatch.setattr("server.connector_engine.discover_connector", lambda url: sample_spec)
    
    response = client.post(
        "/api/connector/discover",
        json={"url": "https://api.acme.com/openapi.json"},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["platform_name"] == "Acme Commerce API"
    assert data["operation_count"] == 1
    assert data["status"] == "draft"
    connector_id = data["id"]
    
    # Test connector list
    list_res = client.get("/api/connector", headers=auth_headers)
    assert list_res.status_code == 200
    connectors = list_res.json()
    assert any(c["id"] == connector_id for c in connectors)
    
    # Test save credentials
    cred_res = client.post(
        f"/api/connector/{connector_id}/credentials",
        json={"credentials": {"api_key": "acme_secret_12345"}},
        headers=auth_headers
    )
    assert cred_res.status_code == 200
    assert cred_res.json()["status"] == "validated"
    
    # Test toggle status (Kill switch)
    toggle_res = client.post(
        f"/api/connector/{connector_id}/toggle",
        json={"active": False},
        headers=auth_headers
    )
    assert toggle_res.status_code == 200
    assert toggle_res.json()["status"] == "disabled"
