# Generation and campaign API

Generation routes require a JWT or an accepted API key. Provider credentials
must be configured on the server; clients never send the server's provider
key.

## Single-copy generation

```http
POST /api/generate
Authorization: Bearer <token-or-api-key>
Content-Type: application/json

{
  "type": "product_description",
  "context": "Insulated stainless-steel bottle for commuters",
  "tone": "professional",
  "variations": 1,
  "max_words": 150
}
```

The type must be one of the values supported by the request model, including
product_description, email_subject, email_body, social_post, ad_headline,
ad_body, landing_page_hero, call_to_action, seo_meta_description, or
blog_intro.

Response shape:

```json
{
  "type": "product_description",
  "variations": ["Generated draft"],
  "output": "Generated draft",
  "generations_used": 1,
  "generations": 4,
  "generation_time_ms": 1200
}
```

Credits are reserved before the provider call. If generation fails, the
reserved credits are refunded. Megastore accounts with an active BYOK key use
the key's provider account and reserve the separate managed server-activity
allowance instead of managed-provider generation credits. The endpoint is
rate-limited and all request fields are bounded.

## Text campaign generation

```http
POST /api/campaign/generate
Authorization: Bearer <token-or-api-key>
Content-Type: application/json

{
  "keyword": "insulated commuter bottle",
  "product_desc": "A leak-resistant stainless-steel bottle designed for daily travel."
}
```

The response contains a campaign identifier, name, and generated assets. Asset
types can include blog content, email drafts, and social posts depending on
the configured provider response.

Generation stores the campaign under the authenticated user. It does not
publish to an external platform.

## Image-assisted campaign generation

```http
POST /api/campaign/generate-vision
Authorization: Bearer <token-or-api-key>
Content-Type: application/json

{
  "image_base64": "<base64 image data>",
  "mime_type": "image/jpeg",
  "keyword": "commuter bottle",
  "extra_context": "Leak-resistant stainless-steel bottle"
}
```

Accepted image types are JPEG, PNG, WebP, and GIF. The decoded upload is
limited to 10 MB. The request model also limits the encoded request field.

## Marketplace listing optimizer

```http
POST /api/optimizer/marketplace-listing
Authorization: Bearer <token-or-api-key>
Content-Type: application/json

{
  "product_name": "Commuter Bottle",
  "platform": "amazon",
  "raw_details": "Insulated stainless steel bottle with a leak-resistant lid",
  "keywords": "commuter bottle, insulated bottle",
  "target_audience": "Daily commuters"
}
```

The platform must be amazon, shopify, etsy, tiktok, tiktok_shop, or ebay.
The response contains platform-specific fields, a structured description, and
a compliance score based on the application rules. Treat AI output as a
draft and verify platform policies and factual product claims before
publishing.

## Competitor review analysis

```http
POST /api/competitor/mine-reviews
Authorization: Bearer <token-or-api-key>
Content-Type: application/json

{
  "product_name": "Commuter Bottle",
  "competitor_name": "Example Brand",
  "reviews_text": "The lid leaked after a week and the finish scratched easily."
}
```

Provide only review text that you are authorized to use. The response contains
extracted complaints, comparison points, a draft counter-description, and
advertising hooks. Do not state unverified advantages as facts.

## Push workflow

Campaign generation and publication are separate. To schedule a controlled
push, call /api/campaign/push with the campaign ID and destinations tied to
user-owned, tested integrations. Review generated assets and destination
metadata before enabling a push.
