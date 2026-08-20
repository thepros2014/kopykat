# ⚡ KopyKat

A fully automated, AI-powered marketing copywriting SaaS.

KopyKat generates high-converting product descriptions, ad copy, emails, and social posts in seconds. It runs on autopilot, featuring automated subscription billing, an SEO blog engine, and background lead generation.

## 🔗 Live Application
**Website:** [kopykat-ai.onrender.com](https://kopykat-ai.onrender.com)

## 📚 Documentation
- **[Month 1 Marketing Playbook](playbook.md):** The exact step-by-step guide to acquiring your first paying customers.
- **[Operator Tutorial](docs/TUTORIAL.md):** How to manage the business, check revenue, update pricing, and handle leads.
- **[Technical Spec Sheet](docs/SPEC_SHEET.md):** Architecture, database schema, API endpoints, and cron job schedules.

## 🛠 Tech Stack
- **Backend:** Python (FastAPI, Uvicorn, SQLAlchemy)
- **Database:** PostgreSQL (Neon.tech)
- **AI Engine:** Google Gemini (`gemini-flash-latest`)
- **Billing:** Stripe (Subscriptions, Generation Packs, Webhooks)
- **Frontend:** Vanilla HTML/CSS/JS
- **Hosting:** Render.com

## 💰 Revenue Flow
```
Customer pays via Stripe → Server grants API access automatically → Stripe auto-deposits to CashApp daily
```

## 🤖 Automated Marketing Engine
This app contains background workers (APScheduler) that run autonomously:
1. **SEO Blog Engine:** Writes and publishes an SEO-optimized article 3x a week.
2. **Email Drip Bot:** Automatically emails free users on Days 1, 3, and 7 to convert them to paid plans.
3. **Opportunity Scout:** Scans Reddit every 4 hours for users complaining about copywriting, drafts an AI reply, and emails the owner the lead.
