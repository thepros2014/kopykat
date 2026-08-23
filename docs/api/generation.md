# API Documentation: Content & Campaign Generation

KopyKat offers copywriting endpoints, multi-channel omni-campaign bundles, Vision AI image-to-copy analyzers, and 1-star competitor review mining.

---

## 1. Single Copy Generator

```http
POST /api/generate
Authorization: Bearer <API_KEY_OR_TOKEN>
Content-Type: application/json

{
  "type": "product_desc",
  "context": "Minimalist stainless steel thermal water bottle, keeps drinks cold 24 hours.",
  "tone": "luxurious and sleek",
  "variations": 1,
  "max_words": 150
}
```

### Response (`200 OK`):
```json
{
  "id": "gen_88f9a0c-...",
  "type": "product_desc",
  "variations": [
    "Engineered from surgical-grade double-walled stainless steel..."
  ],
  "generations_remaining": 999,
  "generated_at": "2026-08-23T00:00:00Z"
}
```

---

## 2. Omni-Channel Campaign Generation

Generates an SEO blog article, a 3-part email drip sequence, and social marketing hooks simultaneously.

```http
POST /api/campaign/generate
Authorization: Bearer <API_KEY_OR_TOKEN>
Content-Type: application/json

{
  "keyword": "Ceramic Pour-Over Coffee Maker",
  "product_desc": "Artisan matte black ceramic pour-over cone with silicone heat-grip ring."
}
```

### Response (`200 OK`):
```json
{
  "id": "camp_55a10e-...",
  "campaign": {
    "assets": {
      "blog_post": {
        "title": "Why Ceramic Pour-Over Unlocks True Coffee Flavor Notes",
        "content": "<p>When brewing single-origin coffees...</p>"
      },
      "email_drip": [
        { "subject": "Welcome to Better Coffee", "body": "..." },
        { "subject": "3 Pour-Over Mistakes to Avoid", "body": "..." },
        { "subject": "Special Offer for Coffee Enthusiasts", "body": "..." }
      ]
    }
  }
}
```

---

## 3. Vision AI (Image-to-Campaign)

Analyzes a raw product photo, detects the item and features, and crafts multi-channel marketing campaigns.

```http
POST /api/campaign/generate-vision
Authorization: Bearer <API_KEY_OR_TOKEN>
Content-Type: application/json

{
  "image_base64": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
  "mime_type": "image/jpeg",
  "keyword": "Running Sneakers",
  "extra_context": "Trail running shoe with carbon fiber plate"
}
```

---

## 4. Competitor 1-Star Review Miner

Ingests customer complaints from competitor listings to generate counter-copy, "Us vs. Them" comparison matrices, and direct-response ad angles.

```http
POST /api/competitor/mine-reviews
Authorization: Bearer <API_KEY_OR_TOKEN>
Content-Type: application/json

{
  "product_name": "UltraShield Pro Backpack",
  "competitor_name": "Generic Pack Co",
  "reviews_text": "The shoulder straps ripped after two weeks. The zipper got stuck constantly and it leaked in light rain."
}
```

### Response (`200 OK`):
```json
{
  "id": "audit_77a88b-...",
  "product_name": "UltraShield Pro Backpack",
  "competitor_name": "Generic Pack Co",
  "extracted_flaws": [
    "Weak shoulder strap stitching prone to tearing",
    "Flimsy zippers that jam easily",
    "Poor water resistance leaking in light rain"
  ],
  "counter_description": "Unlike flimsy alternatives with cheap zippers...",
  "comparison_points": [
    {
      "aspect": "Strap Durability",
      "competitor_flaw": "Tears within weeks",
      "our_advantage": "Military-grade box-stitched Kevlar webbing"
    }
  ],
  "ad_hooks": [
    "Tired of backpack straps snapping mid-commute? Meet UltraShield."
  ]
}
```
