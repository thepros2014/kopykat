import base64
import hashlib
import hmac
import pytest
from server.connector_engine import (
    ConnectorError,
    SafeAsyncHTTPClient,
    SSRFError,
    validate_ip_address,
    validate_public_url,
)
from server.integrations import (
    AmazonConnector,
    ConnectorAuthError,
    ConnectorRateLimitError,
    ConnectorValidationError,
    ConnectorNetworkError,
    EBayConnector,
    EtsyConnector,
    PlatformConnector,
    ShopifyConnector,
    TemuConnector,
    TikTokShopConnector,
    WalmartConnector,
    WooCommerceConnector,
    _handle_http_errors,
    get_connector,
)


def test_validate_ip_address_blocks_private():
    with pytest.raises(SSRFError):
        validate_ip_address("127.0.0.1")

    with pytest.raises(SSRFError):
        validate_ip_address("10.0.0.1")

    with pytest.raises(SSRFError):
        validate_ip_address("169.254.169.254")

    with pytest.raises(SSRFError):
        validate_ip_address("::1")


def test_validate_ip_address_allows_public():
    # Public IP should pass without exception
    validate_ip_address("93.184.216.34")


def test_platform_connector_protocol_conformance():
    connectors = [
        AmazonConnector(),
        ShopifyConnector(),
        EtsyConnector(),
        TikTokShopConnector(),
        EBayConnector(),
        WalmartConnector(),
        TemuConnector(),
        WooCommerceConnector(),
    ]
    for c in connectors:
        assert isinstance(c, PlatformConnector)
        assert isinstance(c.platform_name, str)


def test_get_connector_factory():
    assert isinstance(get_connector("shopify"), ShopifyConnector)
    assert isinstance(get_connector("amazon"), AmazonConnector)
    assert isinstance(get_connector("etsy"), EtsyConnector)
    assert isinstance(get_connector("tiktok"), TikTokShopConnector)
    assert isinstance(get_connector("tiktok_shop"), TikTokShopConnector)
    assert isinstance(get_connector("ebay"), EBayConnector)
    assert isinstance(get_connector("walmart"), WalmartConnector)
    assert isinstance(get_connector("temu"), TemuConnector)
    assert isinstance(get_connector("woocommerce"), WooCommerceConnector)
    assert isinstance(get_connector("woo"), WooCommerceConnector)

    with pytest.raises(ValueError):
        get_connector("unsupported_platform_xyz")


def test_webhook_hmac_verification_all_platforms():
    payload = b'{"event": "stock_update", "sku": "ITEM-123", "quantity": 10}'
    secret = "test_webhook_secret_key"

    # 1. Shopify: Base64 HMAC-SHA256
    shopify = ShopifyConnector()
    sh_sig = base64.b64encode(hmac.new(secret.encode(), payload, hashlib.sha256).digest()).decode()
    assert shopify.verify_webhook({"x-shopify-hmac-sha256": sh_sig}, payload, secret) is True
    assert shopify.verify_webhook({"X-Shopify-Hmac-SHA256": sh_sig}, payload, secret) is True
    assert shopify.verify_webhook({"x-shopify-hmac-sha256": "bad_sig"}, payload, secret) is False
    assert shopify.verify_webhook({}, payload, secret) is False

    # 2. Amazon: Hex HMAC-SHA256
    amazon = AmazonConnector()
    amz_sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert amazon.verify_webhook({"x-amz-signature": amz_sig}, payload, secret) is True
    assert amazon.verify_webhook({"x-amzn-signature": amz_sig}, payload, secret) is True
    assert amazon.verify_webhook({"signature": amz_sig}, payload, secret) is True
    assert amazon.verify_webhook({"x-amz-signature": "bad"}, payload, secret) is False

    # 3. Etsy: Hex HMAC-SHA256
    etsy = EtsyConnector()
    etsy_sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert etsy.verify_webhook({"x-etsy-signature": etsy_sig}, payload, secret) is True
    assert etsy.verify_webhook({"x-etsy-hmac-sha256": etsy_sig}, payload, secret) is True
    assert etsy.verify_webhook({"x-etsy-signature": "bad"}, payload, secret) is False

    # 4. TikTok Shop: Hex HMAC-SHA256
    tiktok = TikTokShopConnector()
    tts_sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert tiktok.verify_webhook({"authorization": tts_sig}, payload, secret) is True
    assert tiktok.verify_webhook({"x-tts-signature": tts_sig}, payload, secret) is True
    assert tiktok.verify_webhook({"authorization": "bad"}, payload, secret) is False

    # 5. eBay: Hex HMAC-SHA256
    ebay = EBayConnector()
    ebay_sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert ebay.verify_webhook({"x-ebay-signature": ebay_sig}, payload, secret) is True
    assert ebay.verify_webhook({"x-ebay-signature": "bad"}, payload, secret) is False

    # 6. Walmart: Hex HMAC-SHA256
    walmart = WalmartConnector()
    wmt_sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert walmart.verify_webhook({"x-walmart-signature": wmt_sig}, payload, secret) is True

    # 7. Temu: Hex HMAC-SHA256
    temu = TemuConnector()
    temu_sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert temu.verify_webhook({"x-temu-signature": temu_sig}, payload, secret) is True

    # 8. WooCommerce: Base64 HMAC-SHA256
    woo = WooCommerceConnector()
    woo_sig = base64.b64encode(hmac.new(secret.encode(), payload, hashlib.sha256).digest()).decode()
    assert woo.verify_webhook({"x-wc-webhook-signature": woo_sig}, payload, secret) is True
    assert woo.verify_webhook({"x-wc-webhook-signature": "bad"}, payload, secret) is False


@pytest.mark.asyncio
async def test_connector_missing_credentials_auth_errors():
    with pytest.raises(ConnectorAuthError):
        await AmazonConnector().fetch_catalog({})
    with pytest.raises(ConnectorAuthError):
        await AmazonConnector().push_product({}, {"sku": "SKU1"})
    with pytest.raises(ConnectorAuthError):
        await AmazonConnector().update_stock({}, "SKU1", 5)

    with pytest.raises(ConnectorAuthError):
        await EtsyConnector().fetch_catalog({})
    with pytest.raises(ConnectorAuthError):
        await EtsyConnector().push_product({}, {"sku": "SKU1"})
    with pytest.raises(ConnectorAuthError):
        await EtsyConnector().update_stock({}, "SKU1", 5)

    with pytest.raises(ConnectorAuthError):
        await TikTokShopConnector().fetch_catalog({})
    with pytest.raises(ConnectorAuthError):
        await TikTokShopConnector().push_product({}, {"sku": "SKU1"})
    with pytest.raises(ConnectorAuthError):
        await TikTokShopConnector().update_stock({}, "SKU1", 5)

    with pytest.raises(ConnectorAuthError):
        await EBayConnector().fetch_catalog({})
    with pytest.raises(ConnectorAuthError):
        await EBayConnector().push_product({}, {"sku": "SKU1"})
    with pytest.raises(ConnectorAuthError):
        await EBayConnector().update_stock({}, "SKU1", 5)


@pytest.mark.asyncio
async def test_connector_validation_errors_missing_sku():
    with pytest.raises(ConnectorValidationError):
        await AmazonConnector().push_product({"access_token": "token"}, {"title": "No SKU"})

    with pytest.raises(ConnectorValidationError):
        await EBayConnector().push_product({"access_token": "token"}, {"title": "No SKU"})


def test_connector_http_error_mapping():
    with pytest.raises(ConnectorAuthError):
        _handle_http_errors(401, "unauthorized", "test")
    with pytest.raises(ConnectorAuthError):
        _handle_http_errors(403, "forbidden", "test")
    with pytest.raises(ConnectorRateLimitError) as exc_info:
        _handle_http_errors(429, "rate limit", "test")
    assert exc_info.value.retry_after_seconds == 60.0

    with pytest.raises(ConnectorValidationError):
        _handle_http_errors(422, "validation error", "test")
    with pytest.raises(ConnectorValidationError):
        _handle_http_errors(400, "bad request", "test")

    with pytest.raises(ConnectorNetworkError):
        _handle_http_errors(500, "server error", "test")
    with pytest.raises(ConnectorNetworkError):
        _handle_http_errors(503, "service unavailable", "test")

