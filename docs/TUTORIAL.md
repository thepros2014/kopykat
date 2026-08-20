# 🛠 SnapCopy AI — Owner's Tutorial & Manual

This guide explains how to operate, manage, and modify your automated SaaS business.

## 1. Checking Your Revenue & Stats
You don't need to log into Stripe to see how much money you made.
Open your terminal or use curl to hit your admin endpoint with your secret header:
```bash
curl -H "x-admin-secret: YOUR_ADMIN_SECRET" https://snapcopy-ai.onrender.com/admin/revenue
```
*(Replace `YOUR_ADMIN_SECRET` with the value in your Render environment variables).*

## 2. Managing the AI Blog
The AI writes posts automatically on Mon, Wed, and Fri. 
**To force it to write a post immediately:**
Trigger it via curl with your admin header:
```bash
curl -H "x-admin-secret: YOUR_ADMIN_SECRET" https://snapcopy-ai.onrender.com/admin/trigger-seo
```
Wait about 20 seconds, then check `https://snapcopy-ai.onrender.com/blog`.

## 3. Handling Leads (Opportunity Scout)
Every 4 hours, the server checks Reddit. If it finds someone complaining about writing copy, you will get an email (sent to the address in your `OWNER_EMAIL` environment variable).
1. Open the email.
2. Click the Reddit link.
3. Copy the AI-generated reply from the email.
4. Paste it into Reddit and hit "Reply".
*This is the highest-converting way to get customers without spending money on ads.*

## 4. How to Update Pricing in the Future
If you want to raise your prices (e.g., changing Basic from $9 to $12):
1. Go to your **Stripe Dashboard** -> Products.
2. Find the "Basic Plan".
3. Add a new price for $12.00 and set it as the default.
4. Copy the new Price ID (`price_...`).
5. Go to **Render** -> Environment Variables.
6. Replace `STRIPE_PRICE_BASIC` with the new ID.
7. Click Save (Render will automatically redeploy).
8. Finally, open `frontend/index.html` on GitHub, find where it says "$9", change it to "$12", and commit the change.

## 5. Changing the AI Model
Currently, you are using `gemini-flash-latest`, which is extremely fast and cheap.
If Google releases a smarter model (e.g., `gemini-pro-latest`) and you want to use it:
1. Go to Render -> Environment Variables.
2. Change the `GEMINI_MODEL` variable to the new model name.
3. Save and let it restart.

## 6. How to Run It Locally (On your PC)
If you ever want to test changes on your Windows machine before pushing them live:
1. Open PowerShell.
2. Navigate to your project: `cd C:\Users\plumb\Desktop\claude-project`
3. Activate virtual environment (if you use one), or just run:
   `pip install -r requirements.txt`
4. Start the server:
   `python -m uvicorn server.main:app --reload`
5. Open your browser to `http://127.0.0.1:8000`.

## 7. Adding New Copywriting Formats
Right now, the AI can generate Product Descriptions, Ads, Emails, etc.
To add a new format (e.g., "Tinder Bios"):
1. Edit `server/models.py` and add `"tinder_bio"` to the `COPY_TYPES` list.
2. Edit `server/ai_engine.py` and add a new prompt template to the `PROMPTS` dictionary.
3. Edit `frontend/dashboard.html` to add the new option to the dropdown menu.
4. Commit and push to GitHub!
