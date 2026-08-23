"""Validated connector registry and restricted HTTP execution runtime."""
from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests

from .connector_engine import ConnectorError, SafeAsyncHTTPClient, validate_public_url

MAX_RESPONSE_BYTES = 2_000_000
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


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
    merged_headers = {"Accept": "application/json", **(headers or {}), **(auth_headers or {})}
    response = requests.request(operation["method"], url, params=query or {}, json=json_body, headers=merged_headers, timeout=(5, 30), allow_redirects=False, stream=True)
    if 300 <= response.status_code < 400:
        response.close()
        raise ConnectorError("Redirects are disabled for connector execution.")
    body = response.raw.read(MAX_RESPONSE_BYTES + 1)
    response.close()
    if len(body) > MAX_RESPONSE_BYTES:
        raise ConnectorError("Connector response exceeds the size limit.")
    try:
        data = response.json() if body else None
    except ValueError:
        data = body.decode("utf-8", errors="replace")
    return {"status_code": response.status_code, "data": data}


async def async_execute_operation(spec: dict[str, Any], operation_name: str, *, path_params: dict[str, str] | None = None, query: dict[str, str] | None = None, json_body: dict[str, Any] | None = None, headers: dict[str, str] | None = None, auth_headers: dict[str, str] | None = None, timeout_seconds: float = 15.0) -> dict[str, Any]:
    operation = find_operation(spec, operation_name)
    path = operation["path"]
    for key, value in (path_params or {}).items():
        path = path.replace("{" + key + "}", str(value))
    url = urljoin(spec["base_url"] + "/", path.lstrip("/"))
    validate_public_url(url)
    merged_headers = {"Accept": "application/json", **(headers or {}), **(auth_headers or {})}
    async with SafeAsyncHTTPClient(timeout_seconds=timeout_seconds, max_response_bytes=MAX_RESPONSE_BYTES) as client:
        response = await client.request(operation["method"], url, params=query, json_body=json_body, headers=merged_headers, allow_redirects=False)
        try:
            data = response.json() if response.content else None
        except ValueError:
            data = response.text
        return {"status_code": response.status_code, "data": data}

