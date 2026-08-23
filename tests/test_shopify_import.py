import pytest
from unittest.mock import patch, MagicMock
from server.shopify_import import clean_html_description, import_shopify_catalog_direct

def test_clean_html_description():
    html = "<p>This is a <strong>premium</strong> leather bag.</p><ul><li>Waterproof</li><li>Reinforced seams</li></ul>"
    clean = clean_html_description(html)
    assert clean == "This is a premium leather bag. Waterproof Reinforced seams"

@pytest.mark.asyncio
async def test_import_shopify_catalog_mocked():
    mock_shopify_response = {
        "products": [
            {
                "id": 123456789,
                "title": "Minimalist Ceramic Mug",
                "body_html": "<p>Handmade artisan ceramic mug.</p>",
                "vendor": "Artisan Goods",
                "tags": "kitchen, mug, coffee",
                "variants": [
                    {"sku": "MUG-WHT-01", "price": "24.00"}
                ],
                "images": [
                    {"src": "https://cdn.shopify.com/mug.jpg"}
                ]
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_shopify_response

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        res = await import_shopify_catalog_direct(
            shop_url="test-store.myshopify.com",
            access_token="shpat_mock_token",
            limit=10
        )

        assert res["success"] is True
        assert res["total_imported"] == 1
        item = res["items"][0]
        assert item["name"] == "Minimalist Ceramic Mug"
        assert item["desc"] == "Handmade artisan ceramic mug."
        assert item["sku"] == "MUG-WHT-01"
        assert item["price"] == 24.0
        assert item["image_url"] == "https://cdn.shopify.com/mug.jpg"

def test_shopify_import_endpoint_unconfigured(client, auth_headers):
    # Without credentials or connected Shopify account, returns clear error response
    res = client.post(
        "/api/catalog/import-shopify",
        json={},
        headers=auth_headers
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert "Please provide your Shopify store URL" in data["error"]
