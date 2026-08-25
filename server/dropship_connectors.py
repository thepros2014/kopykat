"""
dropship_connectors.py
Pre-built connector specifications for verified dropship API partners.

Each spec follows the version-1 format accepted by validate_connector_spec()
in connector_registry.py. They are stored as Python dicts so they can be
inserted into a user's CustomConnector table with a single API call.

All companies listed here have publicly documented REST APIs. This module
is for convenience only; KopyKat does not endorse or certify any vendor.
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Partner metadata (public directory data - no secrets)
# ---------------------------------------------------------------------------

PARTNERS: dict[str, dict[str, Any]] = {
    "printful": {
        "key": "printful",
        "name": "Printful",
        "niche": "Print-on-Demand — Apparel, Accessories, Home",
        "description": (
            "Printful handles printing, fulfilment, and shipping for custom-branded "
            "products. Orders route automatically via their REST API."
        ),
        "docs_url": "https://developers.printful.com/docs/",
        "api_base": "https://api.printful.com",
        "auth_type": "bearer",
        "regions": ["Global"],
        "paid_placement": True,
    },
    "printify": {
        "key": "printify",
        "name": "Printify",
        "niche": "Print-on-Demand — 900+ Products",
        "description": (
            "Printify connects you to a global network of print providers. "
            "Their API manages shops, products, and order submission."
        ),
        "docs_url": "https://printify.com/app/store/api",
        "api_base": "https://api.printify.com/v1",
        "auth_type": "bearer",
        "regions": ["Global"],
        "paid_placement": True,
    },
    "cjdropshipping": {
        "key": "cjdropshipping",
        "name": "CJ Dropshipping",
        "niche": "General Merchandise — Electronics, Apparel, More",
        "description": (
            "CJ Dropshipping offers a broad catalogue of general merchandise with "
            "warehouses in multiple countries. API supports product listing, "
            "order creation, and tracking queries."
        ),
        "docs_url": "https://developers.cjdropshipping.com/",
        "api_base": "https://developers.cjdropshipping.com/api2.0/v1",
        "auth_type": "api_key",
        "regions": ["CN", "US", "EU"],
        "paid_placement": True,
    },
    "bigbuy": {
        "key": "bigbuy",
        "name": "BigBuy",
        "niche": "European Wholesale — 200,000+ Products",
        "description": (
            "Leading European wholesale and dropshipping distributor. REST API "
            "provides real-time stock, pricing, and order management across the EU."
        ),
        "docs_url": "https://api.bigbuy.eu/",
        "api_base": "https://api.bigbuy.eu/rest",
        "auth_type": "api_key",
        "regions": ["EU"],
        "paid_placement": True,
    },
    "spocket": {
        "key": "spocket",
        "name": "Spocket",
        "niche": "US & EU Suppliers — Fast Shipping",
        "description": (
            "Spocket focuses on US and EU-based suppliers for faster domestic shipping. "
            "API supports product import, order automation, and real-time inventory updates."
        ),
        "docs_url": "https://developer.spocket.co/",
        "api_base": "https://api.spocket.co",
        "auth_type": "oauth2",
        "regions": ["US", "EU"],
        "paid_placement": True,
    },
}

# ---------------------------------------------------------------------------
# Connector specs (version-1 format for validate_connector_spec)
# ---------------------------------------------------------------------------

PRINTFUL_SPEC: dict[str, Any] = {
    "version": 1,
    "status": "draft",
    "platform_name": "Printful",
    "base_url": "https://api.printful.com",
    "auth": {"type": "bearer", "header": "Authorization", "prefix": "Bearer"},
    "operations": [
        {
            "id": "list_products",
            "name": "List Products",
            "method": "GET",
            "path": "/products",
            "description": "Returns all sync products for the authenticated store.",
        },
        {
            "id": "get_product",
            "name": "Get Product",
            "method": "GET",
            "path": "/products/{product_id}",
            "description": "Returns a single sync product with its variants.",
            "path_params": [{"name": "product_id", "type": "string", "required": True}],
        },
        {
            "id": "list_orders",
            "name": "List Orders",
            "method": "GET",
            "path": "/orders",
            "description": "Returns a list of orders for the store.",
        },
        {
            "id": "create_order",
            "name": "Create Order",
            "method": "POST",
            "path": "/orders",
            "description": "Creates a new order and optionally confirms it for fulfilment.",
        },
        {
            "id": "get_order",
            "name": "Get Order",
            "method": "GET",
            "path": "/orders/{order_id}",
            "description": "Returns order details and current fulfilment status.",
            "path_params": [{"name": "order_id", "type": "string", "required": True}],
        },
        {
            "id": "get_stock",
            "name": "Get Variant Stock",
            "method": "GET",
            "path": "/products/variant/{variant_id}",
            "description": "Returns stock availability for a specific product variant.",
            "path_params": [{"name": "variant_id", "type": "string", "required": True}],
        },
    ],
}

PRINTIFY_SPEC: dict[str, Any] = {
    "version": 1,
    "status": "draft",
    "platform_name": "Printify",
    "base_url": "https://api.printify.com/v1",
    "auth": {"type": "bearer", "header": "Authorization", "prefix": "Bearer"},
    "operations": [
        {
            "id": "list_shops",
            "name": "List Shops",
            "method": "GET",
            "path": "/shops.json",
            "description": "Returns all shops connected to the authenticated account.",
        },
        {
            "id": "list_products",
            "name": "List Products",
            "method": "GET",
            "path": "/shops/{shop_id}/products.json",
            "description": "Returns all products in a given shop.",
            "path_params": [{"name": "shop_id", "type": "string", "required": True}],
        },
        {
            "id": "get_product",
            "name": "Get Product",
            "method": "GET",
            "path": "/shops/{shop_id}/products/{product_id}.json",
            "description": "Returns full product detail including variants and print areas.",
            "path_params": [
                {"name": "shop_id", "type": "string", "required": True},
                {"name": "product_id", "type": "string", "required": True},
            ],
        },
        {
            "id": "create_order",
            "name": "Create Order",
            "method": "POST",
            "path": "/shops/{shop_id}/orders.json",
            "description": "Submits a new order to the print provider.",
            "path_params": [{"name": "shop_id", "type": "string", "required": True}],
        },
        {
            "id": "list_orders",
            "name": "List Orders",
            "method": "GET",
            "path": "/shops/{shop_id}/orders.json",
            "description": "Returns all orders for a shop with current status.",
            "path_params": [{"name": "shop_id", "type": "string", "required": True}],
        },
    ],
}

CJDROPSHIPPING_SPEC: dict[str, Any] = {
    "version": 1,
    "status": "draft",
    "platform_name": "CJ Dropshipping",
    "base_url": "https://developers.cjdropshipping.com/api2.0/v1",
    "auth": {"type": "header", "header": "CJ-Access-Token"},
    "operations": [
        {
            "id": "get_token",
            "name": "Get Access Token",
            "method": "POST",
            "path": "/authentication/getAccessToken",
            "description": "Exchanges API key and email for a time-limited access token.",
        },
        {
            "id": "list_products",
            "name": "List Products",
            "method": "GET",
            "path": "/product/list",
            "description": "Returns a paginated list of products from the CJ catalogue.",
        },
        {
            "id": "get_product",
            "name": "Get Product Detail",
            "method": "GET",
            "path": "/product/query",
            "description": "Returns full product detail including variants and pricing.",
        },
        {
            "id": "create_order",
            "name": "Create Order",
            "method": "POST",
            "path": "/shopping/order/createOrder",
            "description": "Places a new dropship order with the CJ fulfilment network.",
        },
        {
            "id": "query_order",
            "name": "Query Order",
            "method": "GET",
            "path": "/shopping/order/getOrderDetail",
            "description": "Returns current order status and tracking information.",
        },
    ],
}

BIGBUY_SPEC: dict[str, Any] = {
    "version": 1,
    "status": "draft",
    "platform_name": "BigBuy",
    "base_url": "https://api.bigbuy.eu/rest",
    "auth": {"type": "bearer", "header": "Authorization", "prefix": "Bearer"},
    "operations": [
        {
            "id": "get_catalogue",
            "name": "Get Product Catalogue",
            "method": "GET",
            "path": "/catalog/products.json",
            "description": "Returns the full BigBuy product catalogue with pricing.",
        },
        {
            "id": "get_product",
            "name": "Get Product",
            "method": "GET",
            "path": "/catalog/product/{sku}.json",
            "description": "Returns full detail for a single product by SKU.",
            "path_params": [{"name": "sku", "type": "string", "required": True}],
        },
        {
            "id": "get_stock",
            "name": "Get Stock",
            "method": "GET",
            "path": "/catalog/productsstockavailable.json",
            "description": "Returns current stock availability across all products.",
        },
        {
            "id": "create_order",
            "name": "Create Order",
            "method": "POST",
            "path": "/order/create.json",
            "description": "Submits a new order for fulfilment and European shipping.",
        },
        {
            "id": "get_order",
            "name": "Get Order",
            "method": "GET",
            "path": "/order/orders/{order_id}.json",
            "description": "Returns order status, tracking, and line item detail.",
            "path_params": [{"name": "order_id", "type": "string", "required": True}],
        },
    ],
}

SPOCKET_SPEC: dict[str, Any] = {
    "version": 1,
    "status": "draft",
    "platform_name": "Spocket",
    "base_url": "https://api.spocket.co",
    "auth": {"type": "oauth2", "header": "Authorization", "prefix": "Bearer"},
    "operations": [
        {
            "id": "list_products",
            "name": "List Products",
            "method": "GET",
            "path": "/products",
            "description": "Returns products available from Spocket US/EU suppliers.",
        },
        {
            "id": "import_product",
            "name": "Import Product",
            "method": "POST",
            "path": "/imports",
            "description": "Imports a Spocket product into the connected store.",
        },
        {
            "id": "create_order",
            "name": "Create Order",
            "method": "POST",
            "path": "/orders",
            "description": "Places an order with the Spocket supplier network.",
        },
        {
            "id": "get_order",
            "name": "Get Order",
            "method": "GET",
            "path": "/orders/{order_id}",
            "description": "Returns order status and tracking from the supplier.",
            "path_params": [{"name": "order_id", "type": "string", "required": True}],
        },
        {
            "id": "list_inventory",
            "name": "List Inventory",
            "method": "GET",
            "path": "/inventory",
            "description": "Returns current stock levels for imported products.",
        },
    ],
}

# Map partner key -> connector spec
CONNECTOR_SPECS: dict[str, dict[str, Any]] = {
    "printful": PRINTFUL_SPEC,
    "printify": PRINTIFY_SPEC,
    "cjdropshipping": CJDROPSHIPPING_SPEC,
    "bigbuy": BIGBUY_SPEC,
    "spocket": SPOCKET_SPEC,
}