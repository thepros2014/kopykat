"""
shopify_import.py — Direct 1-Click Shopify Catalog Importer for KopyKat.
Pulls complete product listings, descriptions, variants, and media directly
from Shopify Admin API without manual CSV exports.
"""

import logging
import re
from typing import Dict, Any, List
import httpx

logger = logging.getLogger(__name__)


def clean_html_description(html_text: str) -> str:
    """Removes HTML tags from Shopify product descriptions for clean AI ingestion."""
    if not html_text:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', html_text)
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()


async def import_shopify_catalog_direct(
    shop_url: str,
    access_token: str,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Fetches product catalog directly from Shopify Admin API.
    """
    clean_shop = shop_url.strip().lower()
    clean_shop = clean_shop.replace("https://", "").replace("http://", "").rstrip("/")
    if not clean_shop.endswith(".myshopify.com"):
        clean_shop = f"{clean_shop}.myshopify.com"

    endpoint = f"https://{clean_shop}/admin/api/2024-01/products.json?limit={min(limit, 250)}"
    headers = {
        "X-Shopify-Access-Token": access_token.strip(),
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            res = await client.get(endpoint, headers=headers)
            if res.status_code != 200:
                logger.error("Shopify catalog import failed HTTP %d: %s", res.status_code, res.text)
                return {
                    "success": False,
                    "error": f"Shopify returned error {res.status_code}: Please verify your store URL and Admin API Access Token."
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
        except Exception as exc:
            logger.exception("Shopify import exception: %s", exc)
            return {
                "success": False,
                "error": f"Connection to Shopify store failed: {str(exc)}"
            }
