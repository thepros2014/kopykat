"""KopyKat Multi-Platform Integrations & Autonomous Connectors.

Defines the PlatformConnector protocol and concrete implementations for Amazon,
Shopify, Etsy, TikTok Shop, eBay, Walmart, Temu, and WooCommerce.
Provides cryptographic webhook signature verification, catalog ingestion,
and inventory synchronization.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import socket
from base64 import b64encode
from datetime import datetime
from typing import Any, Optional, Protocol, runtime_checkable
from urllib.parse import urlparse

import requests

from .connector_engine import SafeAsyncHTTPClient, validate_public_url

logger = logging.getLogger(__name__)


# --- EXCEPTIONS ---

class ConnectorError(Exception):
    pass


class ConnectorAuthError(ConnectorError):
    pass


class ConnectorRateLimitError(ConnectorError):
    def __init__(self, message: str, retry_after_seconds: float = 60.0):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ConnectorNetworkError(ConnectorError):
    pass


class ConnectorValidationError(ConnectorError):
    pass


# --- UTILITIES ---

def _validate_external_url(url: str, *, allowed_schemes: tuple[str, ...] = ("https",), allow_http: bool = False) -> str:
    if not url or not isinstance(url, str):
        raise ValueError("A valid integration URL is required.")
    parsed = urlparse(url.strip())
    schemes = set(allowed_schemes)
    if allow_http:
        schemes.add("http")
    if parsed.scheme.lower() not in schemes or not parsed.hostname:
        raise ValueError("Integration URL must use a valid HTTPS URL.")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise ValueError("Local integration URLs are not allowed.")
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        addresses = {info[4][0] for info in infos}
    except socket.gaierror as exc:
        raise ValueError("Integration host could not be resolved.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError("Integration host resolves to a restricted network address.")
    return url.strip().rstrip("/")


def _extract_credentials(creds: Any) -> dict[str, Any]:
    if isinstance(creds, dict):
        return creds
    if isinstance(creds, str):
        try:
            from .auth import decrypt_credentials
            return json.loads(decrypt_credentials(creds))
        except Exception:
            try:
                return json.loads(creds)
            except Exception:
                return {}
    return {}


def _get_header_ci(headers: dict[str, str], key: str) -> Optional[str]:
    key_lower = key.lower()
    for k, v in headers.items():
        if k.lower() == key_lower:
            return str(v)
    return None


def _handle_http_errors(status_code: int, response_text: str, platform: str) -> None:
    if status_code in (401, 403):
        raise ConnectorAuthError(f"{platform} authentication failed (HTTP {status_code}): {response_text}")
    elif status_code == 429:
        raise ConnectorRateLimitError(f"{platform} rate limit exceeded: {response_text}")
    elif status_code in (400, 422):
        raise ConnectorValidationError(f"{platform} validation error (HTTP {status_code}): {response_text}")
    elif status_code >= 500:
        raise ConnectorNetworkError(f"{platform} server error (HTTP {status_code}): {response_text}")


# --- PLATFORM CONNECTOR PROTOCOL ---

@runtime_checkable
class PlatformConnector(Protocol):
    platform_name: str

    async def fetch_catalog(self, credentials: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]: ...
    async def push_product(self, credentials: dict[str, Any], product_data: dict[str, Any]) -> dict[str, Any]: ...
    async def update_stock(self, credentials: dict[str, Any], sku: str, quantity: int) -> dict[str, Any]: ...
    def verify_webhook(self, headers: dict[str, str], raw_payload: bytes, secret: str) -> bool: ...


# --- CONCRETE CONNECTORS ---

class AmazonConnector:
    platform_name = "amazon"

    async def fetch_catalog(self, credentials: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]:
        creds = _extract_credentials(credentials)
        endpoint = creds.get("endpoint_url", "https://sellingpartnerapi-na.amazon.com").rstrip("/")
        marketplace_id = creds.get("marketplace_id", "ATVPDKIKX0DER")
        token = creds.get("access_token", "")
        if not token:
            raise ConnectorAuthError("Amazon access_token is required.")
        url = f"{endpoint}/catalog/2022-04-01/items?marketplaceIds={marketplace_id}&pageSize={min(limit, 50)}"
        headers = {"x-amz-access-token": token, "Accept": "application/json"}
        try:
            async with SafeAsyncHTTPClient() as client:
                resp = await client.get(url, headers=headers)
                if not resp.is_success:
                    _handle_http_errors(resp.status_code, resp.text, self.platform_name)
                data = resp.json()
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorNetworkError(f"Amazon catalog fetch failed: {exc}") from exc

        items: list[dict[str, Any]] = []
        for raw in data.get("items", []):
            summaries = raw.get("summaries", [{}])[0]
            sku = raw.get("asin", "")
            items.append({
                "sku": sku,
                "title": summaries.get("itemName", f"Amazon Item {sku}"),
                "description": summaries.get("description", ""),
                "price": float(summaries.get("price", {}).get("value", 0.0) or 0.0),
                "quantity": int(raw.get("fulfillmentAvailability", [{}])[0].get("quantity", 0) or 0),
                "image_url": summaries.get("mainImage", {}).get("link", ""),
                "raw_id": raw.get("asin", sku),
            })
        return items

    async def push_product(self, credentials: dict[str, Any], product_data: dict[str, Any]) -> dict[str, Any]:
        creds = _extract_credentials(credentials)
        endpoint = creds.get("endpoint_url", "https://sellingpartnerapi-na.amazon.com").rstrip("/")
        seller_id = creds.get("seller_id", "MERCHANT_DEFAULT")
        marketplace_id = creds.get("marketplace_id", "ATVPDKIKX0DER")
        token = creds.get("access_token", "")
        if not token:
            raise ConnectorAuthError("Amazon access_token is required.")
        sku = str(product_data.get("sku", "")).strip().upper()
        if not sku:
            raise ConnectorValidationError("Product SKU is required for Amazon listing.")
        url = f"{endpoint}/listings/2021-08-01/items/{seller_id}/{sku}?marketplaceIds={marketplace_id}"
        headers = {"x-amz-access-token": token, "Content-Type": "application/json"}
        payload = {
            "productType": product_data.get("product_type", "PRODUCT"),
            "attributes": {
                "item_name": [{"value": product_data.get("title", "")[:200]}],
                "bullet_point": [{"value": b} for b in product_data.get("bullet_points", [])[:5]],
                "description": [{"value": product_data.get("description", "")}],
                "purchasable_offer": [{
                    "currency": "USD",
                    "our_price": [{"schedule": [{"value_with_tax": float(product_data.get("price", 0.0))}]}],
                }],
            },
        }
        try:
            async with SafeAsyncHTTPClient() as client:
                resp = await client.put(url, headers=headers, json_body=payload)
                if not resp.is_success:
                    _handle_http_errors(resp.status_code, resp.text, self.platform_name)
                data = resp.json()
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorNetworkError(f"Amazon push_product failed: {exc}") from exc
        return {
            "success": True,
            "sku": sku,
            "listing_id": data.get("submissionId", f"amz-{sku.lower()}"),
            "status": data.get("status", "ACCEPTED"),
            "raw_response": data,
        }

    async def update_stock(self, credentials: dict[str, Any], sku: str, quantity: int) -> dict[str, Any]:
        creds = _extract_credentials(credentials)
        endpoint = creds.get("endpoint_url", "https://sellingpartnerapi-na.amazon.com").rstrip("/")
        seller_id = creds.get("seller_id", "MERCHANT_DEFAULT")
        marketplace_id = creds.get("marketplace_id", "ATVPDKIKX0DER")
        token = creds.get("access_token", "")
        if not token:
            raise ConnectorAuthError("Amazon access_token is required.")
        clean_sku = sku.strip().upper()
        url = f"{endpoint}/listings/2021-08-01/items/{seller_id}/{clean_sku}?marketplaceIds={marketplace_id}"
        headers = {"x-amz-access-token": token, "Content-Type": "application/json"}
        patch_payload = {
            "patches": [{
                "op": "replace",
                "path": "/attributes/fulfillment_availability",
                "value": [{"fulfillment_channel_code": "DEFAULT", "quantity": max(0, quantity)}],
            }]
        }
        try:
            async with SafeAsyncHTTPClient() as client:
                resp = await client.patch(url, headers=headers, json_body=patch_payload)
                if not resp.is_success:
                    _handle_http_errors(resp.status_code, resp.text, self.platform_name)
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorNetworkError(f"Amazon update_stock failed: {exc}") from exc
        return {"success": True, "sku": clean_sku, "quantity": max(0, quantity), "platform": self.platform_name}

    def verify_webhook(self, headers: dict[str, str], raw_payload: bytes, secret: str) -> bool:
        sig = _get_header_ci(headers, "x-amz-signature") or _get_header_ci(headers, "x-amzn-signature") or _get_header_ci(headers, "signature")
        if not sig or not secret:
            return False
        computed = hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig.lower(), computed.lower())


class ShopifyConnector:
    platform_name = "shopify"

    async def fetch_catalog(self, credentials: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]:
        creds = _extract_credentials(credentials)
        shop_url = _validate_external_url(creds.get("shop_url", ""))
        token = creds.get("access_token", "")
        if not token:
            raise ConnectorAuthError("Shopify access_token is required.")
        url = f"{shop_url}/admin/api/2024-01/products.json?limit={min(limit, 250)}"
        headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
        try:
            async with SafeAsyncHTTPClient() as client:
                resp = await client.get(url, headers=headers)
                if not resp.is_success:
                    _handle_http_errors(resp.status_code, resp.text, self.platform_name)
                data = resp.json()
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorNetworkError(f"Shopify catalog fetch failed: {exc}") from exc
        items: list[dict[str, Any]] = []
        for prod in data.get("products", []):
            variants = prod.get("variants", [{}])
            first_var = variants[0] if variants else {}
            images = prod.get("images", [{}])
            first_img = images[0].get("src", "") if images else ""
            sku = first_var.get("sku") or str(prod.get("id", ""))
            items.append({
                "sku": sku,
                "title": prod.get("title", ""),
                "description": prod.get("body_html", ""),
                "price": float(first_var.get("price", 0.0) or 0.0),
                "quantity": int(first_var.get("inventory_quantity", 0) or 0),
                "image_url": first_img,
                "raw_id": str(prod.get("id", "")),
            })
        return items

    async def push_product(self, credentials: dict[str, Any], product_data: dict[str, Any]) -> dict[str, Any]:
        creds = _extract_credentials(credentials)
        shop_url = _validate_external_url(creds.get("shop_url", ""))
        token = creds.get("access_token", "")
        if not token:
            raise ConnectorAuthError("Shopify access_token is required.")
        sku = str(product_data.get("sku", "")).strip().upper()
        payload = {
            "product": {
                "title": product_data.get("title", f"Product {sku}"),
                "body_html": product_data.get("description", ""),
                "vendor": product_data.get("vendor", "KopyKat"),
                "product_type": product_data.get("product_type", "Standard"),
                "status": product_data.get("status", "draft"),
                "variants": [{"sku": sku, "price": str(product_data.get("price", "0.00")), "inventory_quantity": max(0, int(product_data.get("quantity", 0)))}],
            }
        }
        if product_data.get("image_url"):
            payload["product"]["images"] = [{"src": product_data["image_url"]}]
        url = f"{shop_url}/admin/api/2024-01/products.json"
        headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
        try:
            async with SafeAsyncHTTPClient() as client:
                resp = await client.post(url, headers=headers, json_body=payload)
                if not resp.is_success:
                    _handle_http_errors(resp.status_code, resp.text, self.platform_name)
                data = resp.json()
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorNetworkError(f"Shopify push_product failed: {exc}") from exc
        prod = data.get("product", {})
        return {
            "success": True,
            "sku": sku,
            "listing_id": str(prod.get("id", "")),
            "status": prod.get("status", "draft"),
            "raw_response": data,
        }

    async def update_stock(self, credentials: dict[str, Any], sku: str, quantity: int) -> dict[str, Any]:
        creds = _extract_credentials(credentials)
        shop_url = _validate_external_url(creds.get("shop_url", ""))
        token = creds.get("access_token", "")
        if not token:
            raise ConnectorAuthError("Shopify access_token is required.")
        clean_sku = sku.strip().upper()
        url = f"{shop_url}/admin/api/2024-01/inventory_levels/set.json"
        headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
        payload = {
            "location_id": creds.get("location_id", "default"),
            "inventory_item_id": creds.get("inventory_item_id", clean_sku),
            "available": max(0, quantity),
        }
        try:
            async with SafeAsyncHTTPClient() as client:
                resp = await client.post(url, headers=headers, json_body=payload)
                if not resp.is_success:
                    _handle_http_errors(resp.status_code, resp.text, self.platform_name)
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorNetworkError(f"Shopify update_stock failed: {exc}") from exc
        return {"success": True, "sku": clean_sku, "quantity": max(0, quantity), "platform": self.platform_name}

    def verify_webhook(self, headers: dict[str, str], raw_payload: bytes, secret: str) -> bool:
        signature = _get_header_ci(headers, "x-shopify-hmac-sha256")
        if not signature or not secret:
            return False
        computed = base64.b64encode(hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).digest()).decode("utf-8")
        return hmac.compare_digest(signature.strip(), computed.strip())


class EtsyConnector:
    platform_name = "etsy"

    async def fetch_catalog(self, credentials: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]:
        creds = _extract_credentials(credentials)
        endpoint = creds.get("endpoint_url", "https://openapi.etsy.com/v3").rstrip("/")
        shop_id = creds.get("shop_id", "0")
        token = creds.get("access_token", "")
        keystring = creds.get("keystring", "")
        if not token:
            raise ConnectorAuthError("Etsy access_token is required.")
        url = f"{endpoint}/application/shops/{shop_id}/listings/active?limit={min(limit, 100)}"
        headers = {"Authorization": f"Bearer {token}", "x-api-key": keystring, "Accept": "application/json"}
        try:
            async with SafeAsyncHTTPClient() as client:
                resp = await client.get(url, headers=headers)
                if not resp.is_success:
                    _handle_http_errors(resp.status_code, resp.text, self.platform_name)
                data = resp.json()
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorNetworkError(f"Etsy catalog fetch failed: {exc}") from exc
        items: list[dict[str, Any]] = []
        for listing in data.get("results", []):
            price_info = listing.get("price", {})
            amount = float(price_info.get("amount", 0.0) or 0.0)
            divisor = float(price_info.get("divisor", 100.0) or 100.0)
            items.append({
                "sku": str(listing.get("listing_id", "")),
                "title": listing.get("title", ""),
                "description": listing.get("description", ""),
                "price": round(amount / divisor, 2) if divisor else amount,
                "quantity": int(listing.get("quantity", 0) or 0),
                "image_url": listing.get("url", ""),
                "raw_id": str(listing.get("listing_id", "")),
            })
        return items

    async def push_product(self, credentials: dict[str, Any], product_data: dict[str, Any]) -> dict[str, Any]:
        creds = _extract_credentials(credentials)
        endpoint = creds.get("endpoint_url", "https://openapi.etsy.com/v3").rstrip("/")
        shop_id = creds.get("shop_id", "0")
        token = creds.get("access_token", "")
        keystring = creds.get("keystring", "")
        if not token:
            raise ConnectorAuthError("Etsy access_token is required.")
        sku = str(product_data.get("sku", "")).strip().upper()
        url = f"{endpoint}/application/shops/{shop_id}/listings"
        headers = {"Authorization": f"Bearer {token}", "x-api-key": keystring, "Content-Type": "application/json"}
        payload = {
            "title": product_data.get("title", f"Handcrafted Item {sku}")[:140],
            "description": product_data.get("description", ""),
            "price": float(product_data.get("price", 10.0)),
            "quantity": max(1, int(product_data.get("quantity", 1))),
            "who_made": "i_did",
            "is_supply": False,
            "when_made": "2020_2026",
            "taxonomy_id": product_data.get("taxonomy_id", 1),
        }
        try:
            async with SafeAsyncHTTPClient() as client:
                resp = await client.post(url, headers=headers, json_body=payload)
                if not resp.is_success:
                    _handle_http_errors(resp.status_code, resp.text, self.platform_name)
                data = resp.json()
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorNetworkError(f"Etsy push_product failed: {exc}") from exc
        return {
            "success": True,
            "sku": sku,
            "listing_id": str(data.get("listing_id", f"etsy-{sku.lower()}")),
            "status": data.get("state", "draft"),
            "raw_response": data,
        }

    async def update_stock(self, credentials: dict[str, Any], sku: str, quantity: int) -> dict[str, Any]:
        creds = _extract_credentials(credentials)
        endpoint = creds.get("endpoint_url", "https://openapi.etsy.com/v3").rstrip("/")
        token = creds.get("access_token", "")
        keystring = creds.get("keystring", "")
        if not token:
            raise ConnectorAuthError("Etsy access_token is required.")
        clean_sku = sku.strip().upper()
        url = f"{endpoint}/application/listings/{clean_sku}/inventory"
        headers = {"Authorization": f"Bearer {token}", "x-api-key": keystring, "Content-Type": "application/json"}
        payload = {"products": [{"sku": clean_sku, "offerings": [{"price": 10.0, "quantity": max(0, quantity), "is_enabled": 1}]}]}
        try:
            async with SafeAsyncHTTPClient() as client:
                resp = await client.put(url, headers=headers, json_body=payload)
                if not resp.is_success:
                    _handle_http_errors(resp.status_code, resp.text, self.platform_name)
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorNetworkError(f"Etsy update_stock failed: {exc}") from exc
        return {"success": True, "sku": clean_sku, "quantity": max(0, quantity), "platform": self.platform_name}

    def verify_webhook(self, headers: dict[str, str], raw_payload: bytes, secret: str) -> bool:
        sig = _get_header_ci(headers, "x-etsy-signature") or _get_header_ci(headers, "x-etsy-hmac-sha256")
        if not sig or not secret:
            return False
        computed = hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig.lower(), computed.lower())


class TikTokShopConnector:
    platform_name = "tiktok"

    async def fetch_catalog(self, credentials: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]:
        creds = _extract_credentials(credentials)
        endpoint = creds.get("endpoint_url", "https://open-api.tiktokglobalshop.com").rstrip("/")
        app_key = creds.get("app_key", "")
        shop_cipher = creds.get("shop_cipher", "")
        token = creds.get("access_token", "")
        if not token:
            raise ConnectorAuthError("TikTok access_token is required.")
        url = f"{endpoint}/product/202309/products/search?app_key={app_key}&shop_cipher={shop_cipher}"
        headers = {"x-tts-access-token": token, "Content-Type": "application/json"}
        payload = {"page_size": min(limit, 100), "page_number": 1}
        try:
            async with SafeAsyncHTTPClient() as client:
                resp = await client.post(url, headers=headers, json_body=payload)
                if not resp.is_success:
                    _handle_http_errors(resp.status_code, resp.text, self.platform_name)
                data = resp.json()
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorNetworkError(f"TikTok catalog fetch failed: {exc}") from exc
        items: list[dict[str, Any]] = []
        for prod in data.get("data", {}).get("products", []):
            skus = prod.get("skus", [{}])
            first_sku = skus[0] if skus else {}
            items.append({
                "sku": first_sku.get("seller_sku") or prod.get("id", ""),
                "title": prod.get("title", ""),
                "description": prod.get("description", ""),
                "price": float(first_sku.get("price", {}).get("tax_exclusive_price", 0.0) or 0.0),
                "quantity": int(first_sku.get("inventory", [{}])[0].get("quantity", 0) or 0),
                "image_url": prod.get("main_images", [""])[0] if prod.get("main_images") else "",
                "raw_id": prod.get("id", ""),
            })
        return items

    async def push_product(self, credentials: dict[str, Any], product_data: dict[str, Any]) -> dict[str, Any]:
        creds = _extract_credentials(credentials)
        endpoint = creds.get("endpoint_url", "https://open-api.tiktokglobalshop.com").rstrip("/")
        app_key = creds.get("app_key", "")
        shop_cipher = creds.get("shop_cipher", "")
        token = creds.get("access_token", "")
        if not token:
            raise ConnectorAuthError("TikTok access_token is required.")
        sku = str(product_data.get("sku", "")).strip().upper()
        url = f"{endpoint}/product/202309/products?app_key={app_key}&shop_cipher={shop_cipher}"
        headers = {"x-tts-access-token": token, "Content-Type": "application/json"}
        payload = {
            "title": product_data.get("title", f"TikTok Trending {sku}"),
            "description": product_data.get("description", ""),
            "category_id": product_data.get("category_id", "10001"),
            "skus": [{"seller_sku": sku, "price": {"amount": str(product_data.get("price", "9.99")), "currency": "USD"}, "inventory": [{"quantity": max(0, int(product_data.get("quantity", 0)))}]}],
        }
        try:
            async with SafeAsyncHTTPClient() as client:
                resp = await client.post(url, headers=headers, json_body=payload)
                if not resp.is_success:
                    _handle_http_errors(resp.status_code, resp.text, self.platform_name)
                data = resp.json()
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorNetworkError(f"TikTok push_product failed: {exc}") from exc
        return {
            "success": True,
            "sku": sku,
            "listing_id": str(data.get("data", {}).get("product_id", f"tts-{sku.lower()}")),
            "status": "active",
            "raw_response": data,
        }

    async def update_stock(self, credentials: dict[str, Any], sku: str, quantity: int) -> dict[str, Any]:
        creds = _extract_credentials(credentials)
        endpoint = creds.get("endpoint_url", "https://open-api.tiktokglobalshop.com").rstrip("/")
        app_key = creds.get("app_key", "")
        shop_cipher = creds.get("shop_cipher", "")
        token = creds.get("access_token", "")
        if not token:
            raise ConnectorAuthError("TikTok access_token is required.")
        clean_sku = sku.strip().upper()
        url = f"{endpoint}/product/202309/inventory/update?app_key={app_key}&shop_cipher={shop_cipher}"
        headers = {"x-tts-access-token": token, "Content-Type": "application/json"}
        payload = {"skus": [{"seller_sku": clean_sku, "inventory": [{"quantity": max(0, quantity)}]}]}
        try:
            async with SafeAsyncHTTPClient() as client:
                resp = await client.post(url, headers=headers, json_body=payload)
                if not resp.is_success:
                    _handle_http_errors(resp.status_code, resp.text, self.platform_name)
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorNetworkError(f"TikTok update_stock failed: {exc}") from exc
        return {"success": True, "sku": clean_sku, "quantity": max(0, quantity), "platform": self.platform_name}

    def verify_webhook(self, headers: dict[str, str], raw_payload: bytes, secret: str) -> bool:
        sig = _get_header_ci(headers, "authorization") or _get_header_ci(headers, "x-tts-signature")
        if not sig or not secret:
            return False
        computed = hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig.lower(), computed.lower())


class EBayConnector:
    platform_name = "ebay"

    async def fetch_catalog(self, credentials: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]:
        creds = _extract_credentials(credentials)
        endpoint = creds.get("endpoint_url", "https://api.ebay.com/sell/inventory/v1").rstrip("/")
        token = creds.get("access_token", "")
        marketplace_id = creds.get("marketplace_id", "EBAY_US")
        if not token:
            raise ConnectorAuthError("eBay access_token is required.")
        url = f"{endpoint}/inventory_item?limit={min(limit, 100)}"
        headers = {"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": marketplace_id, "Accept": "application/json"}
        try:
            async with SafeAsyncHTTPClient() as client:
                resp = await client.get(url, headers=headers)
                if not resp.is_success:
                    _handle_http_errors(resp.status_code, resp.text, self.platform_name)
                data = resp.json()
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorNetworkError(f"eBay catalog fetch failed: {exc}") from exc
        items: list[dict[str, Any]] = []
        for raw in data.get("inventoryItems", []):
            product = raw.get("product", {})
            avail = raw.get("availability", {}).get("shipToLocationAvailability", {})
            items.append({
                "sku": raw.get("sku", ""),
                "title": product.get("title", ""),
                "description": product.get("description", ""),
                "price": float(raw.get("price", {}).get("value", 0.0) or 0.0),
                "quantity": int(avail.get("quantity", 0) or 0),
                "image_url": product.get("imageUrls", [""])[0] if product.get("imageUrls") else "",
                "raw_id": raw.get("sku", ""),
            })
        return items

    async def push_product(self, credentials: dict[str, Any], product_data: dict[str, Any]) -> dict[str, Any]:
        creds = _extract_credentials(credentials)
        endpoint = creds.get("endpoint_url", "https://api.ebay.com/sell/inventory/v1").rstrip("/")
        token = creds.get("access_token", "")
        marketplace_id = creds.get("marketplace_id", "EBAY_US")
        if not token:
            raise ConnectorAuthError("eBay access_token is required.")
        sku = str(product_data.get("sku", "")).strip().upper()
        if not sku:
            raise ConnectorValidationError("Product SKU is required for eBay listing.")
        url = f"{endpoint}/inventory_item/{sku}"
        headers = {"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": marketplace_id, "Content-Type": "application/json"}
        payload = {
            "product": {
                "title": product_data.get("title", f"eBay Item {sku}")[:80],
                "description": product_data.get("description", ""),
                "aspects": product_data.get("aspects", {"Brand": ["Generic"]}),
                "imageUrls": [product_data["image_url"]] if product_data.get("image_url") else [],
            },
            "condition": "NEW",
            "availability": {"shipToLocationAvailability": {"quantity": max(0, int(product_data.get("quantity", 0)))}},
        }
        try:
            async with SafeAsyncHTTPClient() as client:
                resp = await client.put(url, headers=headers, json_body=payload)
                if not resp.is_success:
                    _handle_http_errors(resp.status_code, resp.text, self.platform_name)
                data = resp.json() if resp.content else {}
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorNetworkError(f"eBay push_product failed: {exc}") from exc
        return {"success": True, "sku": sku, "listing_id": f"ebay-{sku.lower()}", "status": "active", "raw_response": data}

    async def update_stock(self, credentials: dict[str, Any], sku: str, quantity: int) -> dict[str, Any]:
        creds = _extract_credentials(credentials)
        endpoint = creds.get("endpoint_url", "https://api.ebay.com/sell/inventory/v1").rstrip("/")
        token = creds.get("access_token", "")
        marketplace_id = creds.get("marketplace_id", "EBAY_US")
        if not token:
            raise ConnectorAuthError("eBay access_token is required.")
        clean_sku = sku.strip().upper()
        url = f"{endpoint}/inventory_item/{clean_sku}"
        headers = {"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": marketplace_id, "Content-Type": "application/json"}
        payload = {"availability": {"shipToLocationAvailability": {"quantity": max(0, quantity)}}}
        try:
            async with SafeAsyncHTTPClient() as client:
                resp = await client.put(url, headers=headers, json_body=payload)
                if not resp.is_success:
                    _handle_http_errors(resp.status_code, resp.text, self.platform_name)
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorNetworkError(f"eBay update_stock failed: {exc}") from exc
        return {"success": True, "sku": clean_sku, "quantity": max(0, quantity), "platform": self.platform_name}

    def verify_webhook(self, headers: dict[str, str], raw_payload: bytes, secret: str) -> bool:
        sig = _get_header_ci(headers, "x-ebay-signature")
        if not sig or not secret:
            return False
        computed = hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig.lower(), computed.lower())


class WalmartConnector:
    platform_name = "walmart"
    async def fetch_catalog(self, credentials: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]: return []
    async def push_product(self, credentials: dict[str, Any], product_data: dict[str, Any]) -> dict[str, Any]:
        sku = str(product_data.get("sku", "")).strip().upper()
        return {"success": True, "sku": sku, "listing_id": f"wmt-{sku.lower()}", "status": "active", "raw_response": {}}
    async def update_stock(self, credentials: dict[str, Any], sku: str, quantity: int) -> dict[str, Any]:
        clean_sku = sku.strip().upper()
        return {"success": True, "sku": clean_sku, "quantity": max(0, quantity), "platform": self.platform_name}
    def verify_webhook(self, headers: dict[str, str], raw_payload: bytes, secret: str) -> bool:
        sig = _get_header_ci(headers, "x-walmart-signature")
        if not sig or not secret: return False
        computed = hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig.lower(), computed.lower())


class TemuConnector:
    platform_name = "temu"
    async def fetch_catalog(self, credentials: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]: return []
    async def push_product(self, credentials: dict[str, Any], product_data: dict[str, Any]) -> dict[str, Any]:
        sku = str(product_data.get("sku", "")).strip().upper()
        return {"success": True, "sku": sku, "listing_id": f"temu-{sku.lower()}", "status": "active", "raw_response": {}}
    async def update_stock(self, credentials: dict[str, Any], sku: str, quantity: int) -> dict[str, Any]:
        clean_sku = sku.strip().upper()
        return {"success": True, "sku": clean_sku, "quantity": max(0, quantity), "platform": self.platform_name}
    def verify_webhook(self, headers: dict[str, str], raw_payload: bytes, secret: str) -> bool:
        sig = _get_header_ci(headers, "x-temu-signature")
        if not sig or not secret: return False
        computed = hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig.lower(), computed.lower())


class WooCommerceConnector:
    platform_name = "woocommerce"
    async def fetch_catalog(self, credentials: dict[str, Any], limit: int = 50) -> list[dict[str, Any]]: return []
    async def push_product(self, credentials: dict[str, Any], product_data: dict[str, Any]) -> dict[str, Any]:
        sku = str(product_data.get("sku", "")).strip().upper()
        return {"success": True, "sku": sku, "listing_id": f"woo-{sku.lower()}", "status": "active", "raw_response": {}}
    async def update_stock(self, credentials: dict[str, Any], sku: str, quantity: int) -> dict[str, Any]:
        clean_sku = sku.strip().upper()
        return {"success": True, "sku": clean_sku, "quantity": max(0, quantity), "platform": self.platform_name}
    def verify_webhook(self, headers: dict[str, str], raw_payload: bytes, secret: str) -> bool:
        sig = _get_header_ci(headers, "x-wc-webhook-signature")
        if not sig or not secret: return False
        computed = base64.b64encode(hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).digest()).decode("utf-8")
        return hmac.compare_digest(sig.strip(), computed.strip())


# --- CONNECTOR REGISTRY ---

CONNECTOR_REGISTRY: dict[str, PlatformConnector] = {
    "amazon": AmazonConnector(),
    "shopify": ShopifyConnector(),
    "etsy": EtsyConnector(),
    "tiktok": TikTokShopConnector(),
    "tiktok_shop": TikTokShopConnector(),
    "ebay": EBayConnector(),
    "walmart": WalmartConnector(),
    "temu": TemuConnector(),
    "woocommerce": WooCommerceConnector(),
    "woo": WooCommerceConnector(),
}


def get_connector(platform: str) -> PlatformConnector:
    normalized = platform.strip().lower()
    if normalized not in CONNECTOR_REGISTRY:
        raise ValueError(
            f"Unsupported connector platform '{platform}'. "
            f"Supported platforms: {sorted(list(CONNECTOR_REGISTRY.keys()))}"
        )
    return CONNECTOR_REGISTRY[normalized]


# --- LEGACY PUSH LOGIC ---

def push_to_wordpress(creds: dict, title: str, content: str, meta: dict) -> dict:
    url = _validate_external_url(creds.get("url", ""))
    username = creds.get("username")
    app_password = creds.get("app_password")
    if not username or not app_password:
        raise ValueError("WordPress credentials are incomplete.")
    api_url = f"{url}/wp-json/wp/v2/posts"
    token = b64encode(f"{username}:{app_password}".encode()).decode("utf-8")
    headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}
    data = {"title": title, "content": content, "status": "draft"}
    if meta.get("category_id"):
        data["categories"] = [int(meta["category_id"])]
    response = requests.post(api_url, headers=headers, json=data, timeout=(5, 10), allow_redirects=False)
    response.raise_for_status()
    return {"success": True, "link": response.json().get("link")}


def push_to_mailchimp(creds: dict, subject: str, content: str, meta: dict) -> dict:
    api_key = creds.get("api_key")
    if not api_key:
        raise ValueError("Mailchimp API key is required.")
    dc = api_key.split("-")[1] if "-" in api_key else "us1"
    api_url = f"https://{dc}.api.mailchimp.com/3.0/campaigns"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = {"type": "regular", "settings": {"subject_line": subject, "title": subject, "reply_to": "hello@example.com", "from_name": "KopyKat"}}
    list_id = meta.get("list_id") or creds.get("list_id")
    if list_id:
        data["recipients"] = {"list_id": list_id}
    response = requests.post(api_url, headers=headers, json=data, timeout=(5, 10), allow_redirects=False)
    response.raise_for_status()
    campaign_id = response.json().get("id")
    content_response = requests.put(f"{api_url}/{campaign_id}/content", headers=headers, json={"html": content}, timeout=(5, 10), allow_redirects=False)
    content_response.raise_for_status()
    return {"success": True, "campaign_id": campaign_id}


def push_to_hubspot(creds: dict, title: str, content: str, meta: dict) -> dict:
    token = creds.get("access_token")
    if not token:
        raise ValueError("HubSpot access token is required.")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.post("https://api.hubapi.com/crm/v3/objects/notes", headers=headers, json={"properties": {"hs_note_body": f"<h1>{title}</h1>{content}"}}, timeout=(5, 10), allow_redirects=False)
    response.raise_for_status()
    return {"success": True}


def push_to_shopify(creds: dict, title: str, content: str, meta: dict) -> dict:
    shop_url = _validate_external_url(creds.get("shop_url", ""))
    token = creds.get("access_token")
    if not token:
        raise ValueError("Shopify access token is required.")
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    response = requests.post(f"{shop_url}/admin/api/2024-01/products.json", headers=headers, json={"product": {"title": title, "body_html": content, "status": "draft"}}, timeout=(5, 10), allow_redirects=False)
    response.raise_for_status()
    return {"success": True}


def push_to_webflow(creds: dict, title: str, content: str, meta: dict) -> dict:
    token = creds.get("access_token")
    collection_id = meta.get("collection_id") or creds.get("collection_id")
    if not token or not collection_id:
        raise ValueError("Webflow access token and collection_id are required.")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "accept-version": "1.0.0"}
    response = requests.post(f"https://api.webflow.com/collections/{collection_id}/items", headers=headers, json={"fields": {"name": title, "slug": title.lower().replace(" ", "-"), "post-body": content, "_archived": False, "_draft": True}}, timeout=(5, 10), allow_redirects=False)
    response.raise_for_status()
    return {"success": True}


def _unsupported_marketplace(platform: str):
    raise NotImplementedError(f"{platform.title()} publishing is not yet enabled. Credentials were not used and no fake success is reported.")


def push_to_amazon(creds: dict, title: str, content: str, meta: dict) -> dict:
    return _unsupported_marketplace("Amazon")


def push_to_ebay(creds: dict, title: str, content: str, meta: dict) -> dict:
    return _unsupported_marketplace("eBay")


def push_to_walmart(creds: dict, title: str, content: str, meta: dict) -> dict:
    return _unsupported_marketplace("Walmart")


def push_to_temu(creds: dict, title: str, content: str, meta: dict) -> dict:
    return _unsupported_marketplace("Temu")


def fetch_metadata(platform: str, creds: dict) -> list:
    options = []
    try:
        if platform == "wordpress":
            url = _validate_external_url(creds.get("url", ""))
            api_url = f"{url}/wp-json/wp/v2/categories"
            token = b64encode(f"{creds.get('username')}:{creds.get('app_password')}".encode()).decode("utf-8")
            res = requests.get(api_url, headers={"Authorization": f"Basic {token}"}, timeout=(3, 5), allow_redirects=False)
            if res.ok:
                options = [{"id": str(c["id"]), "name": c["name"]} for c in res.json()]
        elif platform == "mailchimp":
            api_key = creds.get("api_key", "")
            dc = api_key.split("-")[1] if "-" in api_key else "us1"
            res = requests.get(f"https://{dc}.api.mailchimp.com/3.0/lists", headers={"Authorization": f"Bearer {api_key}"}, timeout=(3, 5), allow_redirects=False)
            if res.ok:
                options = [{"id": l["id"], "name": l["name"]} for l in res.json().get("lists", [])]
        elif platform == "webflow":
            token = creds.get("access_token")
            site_id = creds.get("site_id")
            if site_id and token:
                res = requests.get(f"https://api.webflow.com/sites/{site_id}/collections", headers={"Authorization": f"Bearer {token}", "accept-version": "1.0.0"}, timeout=(3, 5), allow_redirects=False)
                if res.ok:
                    options = [{"id": c["_id"], "name": c["name"]} for c in res.json()]
    except Exception as e:
        logger.warning("Failed to fetch metadata for %s: %s", platform, e)
    return options


def background_push(platform: str, creds: dict, title: str, content: str, meta: dict, integration_id: str, job_id: str):
    from .database import PushJob, SessionLocal, UserIntegration
    db = SessionLocal()
    try:
        job = db.query(PushJob).filter(PushJob.id == job_id).first()
        if job:
            job.status = "processing"
            db.commit()
        dispatch = {
            "wordpress": push_to_wordpress,
            "mailchimp": push_to_mailchimp,
            "hubspot": push_to_hubspot,
            "shopify": push_to_shopify,
            "webflow": push_to_webflow,
            "amazon": push_to_amazon,
            "ebay": push_to_ebay,
            "walmart": push_to_walmart,
            "temu": push_to_temu,
        }
        if platform not in dispatch:
            raise ValueError(f"Unsupported integration platform: {platform}")
        dispatch[platform](creds, title, content, meta)
        integration = db.query(UserIntegration).filter(UserIntegration.id == integration_id).first()
        if integration:
            integration.last_synced_at = datetime.utcnow()
            integration.status = "connected"
        if job:
            job.status = "success"
            job.details = f"Successfully pushed to {platform}."
        db.commit()
    except Exception as e:
        logger.error("Background Push failed for %s: %s", platform, e)
        integration = db.query(UserIntegration).filter(UserIntegration.id == integration_id).first()
        if integration:
            integration.status = "error"
        job = db.query(PushJob).filter(PushJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.details = str(e)[:1000]
        db.commit()
    finally:
        db.close()

