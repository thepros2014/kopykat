# KopyKat — Social Opportunity Scout

The Social Opportunity Scout scans public communities (Reddit, forums, marketplaces) every 4 hours for store owners seeking copywriting and catalog solutions, drafting customized, helpful replies for the merchant.

---

## 1. Scanner Workflow

```
+─────────────────────────────────────────────────────────────+
|                    APScheduler (Every 4h)                   |
+─────────────────────────────────────────────────────────────+
                               │
                               ▼
+─────────────────────────────────────────────────────────────+
|                  Scan Subreddits via API                    |
|   (r/entrepreneur, r/smallbusiness, r/ecommerce, etc.)      |
+─────────────────────────────────────────────────────────────+
                               │
                               ▼
+─────────────────────────────────────────────────────────────+
|               Match High-Intent Buying Keywords             |
|   ("write copy", "product descriptions", "copywriter")      |
+─────────────────────────────────────────────────────────────+
                               │
                               ▼
+─────────────────────────────────────────────────────────────+
|                 Draft AI Contextual Reply                   |
|   (Helpful, authentic, non-spammy community response)       |
+─────────────────────────────────────────────────────────────+
                               │
                               ▼
+─────────────────────────────────────────────────────────────+
|          Record in Database & Notify Founder Email          |
+─────────────────────────────────────────────────────────────+
```

---

## 2. Dashboard Integration

All discovered opportunities are streamed live to the **Opportunity Leads** tab in the merchant dashboard with 1-click reply copying and direct links to the live thread.
