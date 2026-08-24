"""
shopify_import.py — Direct 1-Click Shopify Catalog Importer for KopyKat.
Pulls complete product listings, descriptions, variants, and media directly
from Shopify Admin API without manual CSV exports.
"""

import logging
import re
from typing import Dict, Any
from urllib.parse import urlparse
import httpx

logger = logging.getLogger(__name__)
_SHOPIFY_SUFFIX = ".myshopify.com"
_SHOPIFY_STORE_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024


def clean_html_description(html_text: str) -> str:
    """Removes HTML tags from Shopify product descriptions for clean AI ingestion."""
    if not html_text:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', html_text)
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()


def normalize_shopify_domain(shop_url: str) -> str:
    """Return a canonical Shopify-hosted store domain.

    This importer only needs Shopify's canonical ``*.myshopify.com`` host.
    Restricting the destination prevents the catalog token from being sent to
    an arbitrary URL and closes the SSRF-shaped URL normalization bug that
    previously accepted values such as ``evil.example/foo.myshopify.com``.
    """

    raw = (shop_url or "").strip().lower()
    if not raw:
        raise ValueError("A Shopify store URL is required.")
    if "://" not in raw and "." not in raw:
        raw = f"{raw}{_SHOPIFY_SUFFIX}"
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Shopify store URL must use HTTPS.")
    if parsed.username or parsed.password or parsed.port or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Shopify store URL must contain only the store hostname.")

    host = parsed.hostname.rstrip(".")
    if not host.endswith(_SHOPIFY_SUFFIX):
        raise ValueError("Shopify store URL must use a *.myshopify.com hostname.")
    store_name = host[: -len(_SHOPIFY_SUFFIX)]
    if not _SHOPIFY_STORE_RE.fullmatch(store_name):
        raise ValueError("Shopify store hostname is invalid.")
    return host


async def import_shopify_catalog_direct(
    shop_url: str,
    access_token: str,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Fetches product catalog directly from Shopify Admin API.
    """
    clean_shop = normalize_shopify_domain(shop_url)

    endpoint = f"https://{clean_shop}/admin/api/2024-01/products.json?limit={min(limit, 250)}"
    headers = {
        "X-Shopify-Access-Token": access_token.strip(),
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False, trust_env=False) as client:
        try:
            res = await client.get(endpoint, headers=headers)
            if res.status_code != 200:
                logger.warning("Shopify catalog import failed with HTTP %d", res.status_code)
                return {
                    "success": False,
                    "error": f"Shopify returned error {res.status_code}: Please verify your store URL and Admin API Access Token."
                }

            if len(res.content) > _MAX_RESPONSE_BYTES:
                return {
                    "success": False,
                    "error": "Shopify returned a catalog larger than the supported response limit."
                }

            data = res.json()
            products = data.get("products", [])
            parsed_items = []

            for p in products:
                prod_title = p.get("title", "Untitled Product")
                body_html = p.get("body_html", "")
                plain_desc = clean_html_description(body_html) or prod_title
                variants = p.get("variants", [])
                primary_sku = variants[0].get("sku", "") if variants else ""
                price = variants[0].get("price", "0.00") if variants else "0.00"
                images = p.get("images", [])
                image_url = images[0].get("src", "") if images else ""

                parsed_items.append({
                    "id": str(p.get("id")),
                    "name": prod_title,
                    "desc": plain_desc,
                    "sku": primary_sku or f"SHOPIFY-{p.get('id')}",
                    "price": float(price) if price else 0.0,
                    "vendor": p.get("vendor", ""),
                    "tags": p.get("tags", ""),
                    "image_url": image_url
                })

            return {
                "success": True,
                "total_imported": len(parsed_items),
                "items": parsed_items
            }
        except ValueError as exc:
            logger.warning("Shopify import validation failed: %s", exc)
            return {
                "success": False,
                "error": str(exc)
            }
        except Exception:
            logger.exception("Shopify import exception")
            return {
                "success": False,
                "error": "Connection to Shopify store failed. Please verify the store and try again."
            }
