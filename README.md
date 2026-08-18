# ⚡ SnapCopy AI — Setup Guide

A fully automated AI copywriting SaaS. Once deployed, it runs itself and deposits money to your CashApp automatically.

**Total setup time: ~30 minutes. Cost to start: $0.**

---

## 📋 What You Need (All Free)

| Item | Where to get it | Cost |
|------|-----------------|------|
| Google Gemini API key | aistudio.google.com | FREE |
| Stripe account | stripe.com | FREE (2.9% + 30¢ per sale) |
| GitHub account | github.com | FREE |
| Render.com account | render.com | FREE |
| Your CashApp routing # | CashApp → Banking tab | FREE |

---

## STEP 1 — Get Your Free Gemini API Key (5 min)

1. Go to **https://aistudio.google.com/app/apikey**
2. Sign in with your Google account
3. Click **"Create API Key"**
4. Copy it — you'll paste it in Step 4

> No credit card needed. Free tier gives you plenty of requests to start.

---

## STEP 2 — Set Up Stripe (10 min)

### 2a. Create Stripe account
1. Go to **https://stripe.com** → click **"Start now"**
2. Enter your email, name, password
3. Verify your email
4. Complete business info (select "Individual / Sole Proprietor")

### 2b. Connect CashApp for payouts
1. Open **CashApp** on your phone
2. Tap the **💰 Money / Banking** tab
3. Find your **Routing Number** and **Account Number** (under Direct Deposit)
4. In Stripe: go to **Settings → Payouts → Bank Account**
5. Enter your CashApp routing + account numbers
6. Set payout schedule to **"Daily"** (Settings → Payout Schedule)

> Stripe will now automatically wire your earnings to CashApp every day. You do nothing.

### 2c. Create your products in Stripe
Go to **Stripe Dashboard → Products → Add Product** and create these:

| Product | Price | Billing |
|---------|-------|---------|
| Basic Plan | $9.00 | Monthly recurring |
| Pro Plan | $29.00 | Monthly recurring |
| Business Plan | $79.00 | Monthly recurring |
| Starter Pack | $5.00 | One time |
| Growth Pack | $15.00 | One time |
| Scale Pack | $40.00 | One time |

After creating each one, copy its **Price ID** (starts with `price_`). You'll need these in Step 4.

### 2d. Get your Stripe API keys
Go to **Stripe Dashboard → Developers → API keys**
- Copy your **Secret key** (starts with `sk_live_`)

---

## STEP 3 — Push Code to GitHub (5 min)

1. Go to **github.com** → click **"+"** → **"New repository"**
2. Name it `snapcopy-ai`, set to **Public**, click **Create**
3. On your Windows machine, open **PowerShell** in this project folder and run:

```powershell
cd C:\Users\plumb\Desktop\claude-project
git init
git add .
git commit -m "Initial SnapCopy AI build"
git remote add origin https://github.com/YOUR_USERNAME/snapcopy-ai.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your actual GitHub username.

---

## STEP 4 — Deploy to Render.com (10 min)

1. Go to **https://render.com** → Sign up (free)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub account → select your `snapcopy-ai` repo
4. Configure:
   - **Name:** `snapcopy-ai`
   - **Environment:** `Python`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn server.main:app --host 0.0.0.0 --port $PORT`
   - **Plan:** `Free`
5. Click **"Add Environment Variable"** for each of these:

| Key | Value |
|-----|-------|
| `GEMINI_API_KEY` | Your Gemini key from Step 1 |
| `AI_PROVIDER` | `gemini` |
| `STRIPE_SECRET_KEY` | Your Stripe secret key |
| `STRIPE_PRICE_BASIC` | `price_...` from Step 2c |
| `STRIPE_PRICE_PRO` | `price_...` from Step 2c |
| `STRIPE_PRICE_BUSINESS` | `price_...` from Step 2c |
| `STRIPE_PRICE_PACK_STARTER` | `price_...` from Step 2c |
| `STRIPE_PRICE_PACK_GROWTH` | `price_...` from Step 2c |
| `STRIPE_PRICE_PACK_SCALE` | `price_...` from Step 2c |
| `JWT_SECRET_KEY` | Any long random string (32+ chars) |
| `ADMIN_SECRET` | Any secret you'll remember |
| `OWNER_EMAIL` | Your email (for daily reports) |

6. Click **"Create Web Service"**
7. Wait ~3 minutes for it to deploy
8. Copy your app URL (e.g., `https://snapcopy-ai.onrender.com`)

---

## STEP 5 — Set Up Stripe Webhook (5 min)

This is critical — it's how Stripe tells your server about payments.

1. Go to **Stripe Dashboard → Developers → Webhooks**
2. Click **"Add endpoint"**
3. Enter your URL: `https://snapcopy-ai.onrender.com/billing/webhook`
4. Select these events:
   - `customer.subscription.created`
   - `customer.subscription.deleted`
   - `customer.subscription.updated`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
   - `checkout.session.completed`
5. Click **"Add endpoint"**
6. Click **"Reveal"** on the **Signing Secret** → copy it (starts with `whsec_`)
7. Go back to Render → Environment Variables → add:
   - `STRIPE_WEBHOOK_SECRET` = your `whsec_...` value
8. Render will auto-redeploy

---

## STEP 6 — Test It ✅

1. Visit your app: `https://snapcopy-ai.onrender.com`
2. Create a test account → go to Dashboard → create an API key
3. Test the API:

```bash
curl -X POST https://snapcopy-ai.onrender.com/api/generate \
  -H "Authorization: Bearer sc_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{"type":"product_description","context":"Wireless earbuds with 40h battery","tone":"bold"}'
```

4. Test a payment with Stripe test card: `4242 4242 4242 4242` (any exp, any CVC)
5. Check Stripe dashboard to see the test payment

---

## 🎉 You're Live!

From this point on, **everything runs automatically:**

- ✅ Customers sign up and pay at your URL
- ✅ Stripe charges them monthly
- ✅ Your server grants/revokes access automatically
- ✅ AI generates content for customers 24/7
- ✅ Stripe deposits your earnings to CashApp daily
- ✅ You get a revenue report email every morning at 8am

**Check your revenue anytime:**
```bash
curl https://snapcopy-ai.onrender.com/admin/revenue \
  -H "x-admin-secret: YOUR_ADMIN_SECRET"
```

---

## 💰 When Money Starts Coming In

Your Stripe Dashboard → Payouts shows pending balance.  
Stripe holds funds for ~2-7 days on new accounts (standard fraud protection).  
After that, payouts hit your CashApp daily automatically.

To see your CashApp balance, look for deposits from **"Stripe"** or **"Sutton Bank"** (CashApp's partner bank).

---

## 📈 Growing the Business

Once running, here's how to get customers for free:

1. **Reddit** — Post in r/entrepreneur, r/SideProject, r/marketing showing a real example output
2. **ProductHunt** — Submit your app (free, drives thousands of signups)
3. **Twitter/X** — Post before/after copy examples showing quality
4. **SEO** — Your landing page already has SEO meta tags
5. **API directories** — Submit to RapidAPI (free listing, they bring customers to you)

---

## 🆘 Troubleshooting

**Server won't start:** Check Render logs → ensure all env variables are set  
**Payments not working:** Verify webhook URL and `STRIPE_WEBHOOK_SECRET`  
**AI not generating:** Verify `GEMINI_API_KEY` is correct and not expired  
**CashApp not receiving funds:** Verify routing/account numbers in Stripe payout settings  

Need help? Check the API docs at `/api/docs` on your deployed URL.
