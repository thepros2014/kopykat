"""Validated connector registry and restricted HTTP execution runtime."""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin

from .connector_engine import ConnectorError, SafeAsyncHTTPClient, SafeSyncHTTPClient, validate_public_url

MAX_RESPONSE_BYTES = 2_000_000
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_BLOCKED_REQUEST_HEADERS = {
    "connection",
    "content-length",
    "forwarded",
    "host",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "transfer-encoding",
    "upgrade",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
}


def _merge_safe_headers(headers: dict[str, str] | None, auth_headers: dict[str, str] | None) -> dict[str, str]:
    """Merge connector headers while preventing request-smuggling controls."""

    merged: dict[str, str] = {}
    for source in (headers or {}, auth_headers or {}):
        for name, value in source.items():
            if not isinstance(name, str) or not isinstance(value, str):
                raise ConnectorError("Connector headers must be text values.")
            if name.lower() in _BLOCKED_REQUEST_HEADERS:
                raise ConnectorError(f"Connector header {name!r} is not permitted.")
            if any(character in name or character in value for character in ("\r", "\n", "\0")):
                raise ConnectorError("Connector headers cannot contain control characters.")
            if len(name) > 128 or len(value) > 8_192:
                raise ConnectorError("Connector header exceeds the supported size limit.")
            merged[name] = value
    return {"Accept": "application/json", **merged}


def validate_connector_spec(spec: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(spec, dict) or spec.get("version") != 1:
        raise ConnectorError("Unsupported connector specification.")
    if spec.get("status") not in {"draft", "validated", "active"}:
        raise ConnectorError("Invalid connector status.")
    base_url = validate_public_url(str(spec.get("base_url", ""))).rstrip("/")
    operations = spec.get("operations")
    if not isinstance(operations, list) or not operations or len(operations) > 500:
        raise ConnectorError("Connector must contain 1-500 operations.")
    safe_operations = []
    for operation in operations:
        if not isinstance(operation, dict):
            raise ConnectorError("Invalid connector operation.")
        method = str(operation.get("method", "")).upper()
        path = str(operation.get("path", ""))
        if method not in ALLOWED_METHODS or not path.startswith("/") or path.startswith("//"):
            raise ConnectorError("Invalid connector operation path or method.")
        if "?" in path:
            raise ConnectorError("Connector paths must not contain fixed query strings.")
        safe_operations.append({
            "name": str(operation.get("name", ""))[:120],
            "method": method,
            "path": path[:1000],
            "summary": str(operation.get("summary", ""))[:500],
            "tags": [str(x)[:80] for x in operation.get("tags", [])[:10]],
            "security": operation.get("security", []),
        })
    return {
        **spec,
        "base_url": base_url,
        "operations": safe_operations,
        "execution_policy": {
            "allow_arbitrary_code": False,
            "require_https": True,
            "allow_redirects": False,
            "max_operations": 500,
        },
    }


def find_operation(spec: dict[str, Any], name: str) -> dict[str, Any]:
    validated = validate_connector_spec(spec)
    for operation in validated["operations"]:
        if operation["name"] == name:
            return operation
    raise ConnectorError("Requested connector operation was not found.")


def execute_operation(spec: dict[str, Any], operation_name: str, *, path_params: dict[str, str] | None = None, query: dict[str, str] | None = None, json_body: dict[str, Any] | None = None, headers: dict[str, str] | None = None, auth_headers: dict[str, str] | None = None) -> dict[str, Any]:
    operation = find_operation(spec, operation_name)
    path = operation["path"]
    for key, value in (path_params or {}).items():
        path = path.replace("{" + key + "}", str(value))
    url = urljoin(spec["base_url"] + "/", path.lstrip("/"))
    validate_public_url(url)
    merged_headers = _merge_safe_headers(headers, auth_headers)
    with SafeSyncHTTPClient(timeout_seconds=30.0, max_response_bytes=MAX_RESPONSE_BYTES) as client:
        response = client.request(
            operation["method"],
            url,
            params=query or {},
            json_body=json_body,
            headers=merged_headers,
            allow_redirects=False,
        )
    try:
        data = response.json() if response.content else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        data = response.text
    return {"status_code": response.status_code, "data": data}


async def async_execute_operation(spec: dict[str, Any], operation_name: str, *, path_params: dict[str, str] | None = None, query: dict[str, str] | None = None, json_body: dict[str, Any] | None = None, headers: dict[str, str] | None = None, auth_headers: dict[str, str] | None = None, timeout_seconds: float = 15.0) -> dict[str, Any]:
    operation = find_operation(spec, operation_name)
    path = operation["path"]
    for key, value in (path_params or {}).items():
        path = path.replace("{" + key + "}", str(value))
    url = urljoin(spec["base_url"] + "/", path.lstrip("/"))
    validate_public_url(url)
    merged_headers = _merge_safe_headers(headers, auth_headers)
    async with SafeAsyncHTTPClient(timeout_seconds=timeout_seconds, max_response_bytes=MAX_RESPONSE_BYTES) as client:
        response = await client.request(operation["method"], url, params=query, json_body=json_body, headers=merged_headers, allow_redirects=False)
        try:
            data = response.json() if response.content else None
        except ValueError:
            data = response.text
        return {"status_code": response.status_code, "data": data}
