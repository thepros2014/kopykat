"""KopyKat Universal Connector Engine.

Builds a constrained connector specification from an API/OpenAPI document.
It deliberately does NOT execute AI-generated code. Runtime execution should
only consume validated HTTP operation specifications from this module.
"""
from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

MAX_SPEC_BYTES = 2_000_000
ALLOWED_SCHEMES = {"https"}
BLOCKED_HOSTS = {"localhost", "localhost.localdomain"}


class ConnectorError(ValueError):
    pass


def validate_public_url(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ConnectorError("A documentation URL is required.")
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ALLOWED_SCHEMES or not parsed.hostname:
        raise ConnectorError("Connector discovery requires an HTTPS URL.")
    host = parsed.hostname.rstrip(".").lower()
    if host in BLOCKED_HOSTS or host.endswith(".localhost"):
        raise ConnectorError("Local connector URLs are not permitted.")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ConnectorError("Connector host could not be resolved.") from exc
    for raw in addresses:
        ip = ipaddress.ip_address(raw)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ConnectorError("Connector host resolves to a restricted network address.")
    return url.strip()


def fetch_api_document(url: str) -> dict[str, Any]:
    safe_url = validate_public_url(url)
    response = requests.get(
        safe_url,
        headers={"Accept": "application/json, application/yaml, text/yaml"},
        timeout=(5, 15),
        allow_redirects=False,
    )
    if 300 <= response.status_code < 400:
        raise ConnectorError("Redirects are disabled during connector discovery.")
    response.raise_for_status()
    if len(response.content) > MAX_SPEC_BYTES:
        raise ConnectorError("API document exceeds the connector size limit.")
    try:
        document = response.json()
    except ValueError as exc:
        raise ConnectorError("The API document must be JSON/OpenAPI JSON.") from exc
    if not isinstance(document, dict):
        raise ConnectorError("Invalid API document.")
    return document


def _operation_name(method: str, path: str, operation: dict[str, Any]) -> str:
    return str(operation.get("operationId") or f"{method.lower()} {path}")[:120]


def _auth_modes(document: dict[str, Any]) -> list[str]:
    schemes = document.get("components", {}).get("securitySchemes", {})
    modes: list[str] = []
    for value in schemes.values():
        if not isinstance(value, dict):
            continue
        kind = value.get("type")
        if kind == "oauth2": modes.append("oauth2")
        elif kind == "apiKey": modes.append("api_key")
        elif kind == "http" and value.get("scheme", "").lower() == "bearer": modes.append("bearer")
        elif kind == "http" and value.get("scheme", "").lower() == "basic": modes.append("basic")
    return sorted(set(modes))


def build_connector_spec(document: dict[str, Any], source_url: str) -> dict[str, Any]:
    if document.get("openapi", document.get("swagger")) is None:
        raise ConnectorError("Only OpenAPI/Swagger documents are supported.")
    base = document.get("servers", [{}])[0].get("url") if document.get("servers") else None
    if not base:
        base = f"{urlparse(source_url).scheme}://{urlparse(source_url).netloc}"
    base_url = urljoin(source_url, base)
    validate_public_url(base_url)

    operations: list[dict[str, Any]] = []
    for path, path_item in (document.get("paths") or {}).items():
        if not isinstance(path_item, dict) or not isinstance(path, str) or not path.startswith("/"):
            continue
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"} or not isinstance(operation, dict):
                continue
            operations.append({
                "name": _operation_name(method, path, operation),
                "method": method.upper(),
                "path": path,
                "summary": str(operation.get("summary") or operation.get("description") or "")[:500],
                "tags": [str(x)[:80] for x in operation.get("tags", [])[:10]],
                "security": operation.get("security", document.get("security", [])),
            })
    if not operations:
        raise ConnectorError("No supported HTTP operations were found.")
    return {
        "version": 1,
        "platform_name": str(document.get("info", {}).get("title") or "Custom Platform")[:120],
        "source_url": source_url,
        "base_url": base_url.rstrip("/"),
        "authentication_modes": _auth_modes(document),
        "operations": operations[:500],
        "status": "draft",
        "execution_policy": {
            "allow_arbitrary_code": False,
            "allow_redirects": False,
            "require_https": True,
            "max_operations": 500,
        },
    }


def discover_connector(source_url: str) -> dict[str, Any]:
    document = fetch_api_document(source_url)
    return build_connector_spec(document, source_url)
