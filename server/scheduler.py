"""
scheduler.py — Automated background tasks. Runs silently on the server.
No human interaction required.
"""

import logging
import os
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from .database import SessionLocal, User, APIKey, UsageRecord, RevenueRecord

logger = logging.getLogger(__name__)

# ── Email config (optional — for owner reports) ───────────────────────────────

OWNER_EMAIL    = os.getenv("OWNER_EMAIL", "")
SMTP_HOST      = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT      = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER      = os.getenv("SMTP_USER", "")
SMTP_PASSWORD  = os.getenv("SMTP_PASSWORD", "")  # Gmail app password


def _send_email(subject: str, body: str, to: str):
    """Send an email via SMTP. Used only for owner reports."""
    if not all([SMTP_USER, SMTP_PASSWORD, OWNER_EMAIL]):
        logger.info("Email not configured — skipping notification")
        return
    try:
        msg            = MIMEMultipart()
        msg["From"]    = SMTP_USER
        msg["To"]      = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        logger.info(f"Email sent: {subject}")
    except Exception as e:
        logger.error(f"Email send failed: {e}")


# ── Scheduled tasks ───────────────────────────────────────────────────────────

def _reset_daily_api_counters():
    """Resets the 'requests_today' counter on all API keys. Runs at midnight."""
    db: Session = SessionLocal()
    try:
        updated = db.query(APIKey).update({"requests_today": 0})
        db.commit()
        logger.info(f"Daily API counters reset for {updated} keys")
    except Exception as e:
        logger.error(f"Counter reset failed: {e}")
        db.rollback()
    finally:
        db.close()


def _send_daily_revenue_report():
    """
    Compiles today's revenue and sends the owner a summary email.
    Runs every day at 8am UTC.
    """
    if not OWNER_EMAIL:
        return

    db: Session = SessionLocal()
    try:
        from sqlalchemy import func
        now         = datetime.utcnow()
        day_start   = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Today's revenue
        today_rev = db.query(func.sum(RevenueRecord.amount_cents)).filter(
            RevenueRecord.status == "succeeded",
            RevenueRecord.created_at >= day_start,
        ).scalar() or 0

        # Month's revenue
        month_rev = db.query(func.sum(RevenueRecord.amount_cents)).filter(
            RevenueRecord.status == "succeeded",
            RevenueRecord.created_at >= month_start,
        ).scalar() or 0

        # New signups today
        new_users = db.query(func.count(User.id)).filter(
            User.created_at >= day_start
        ).scalar() or 0

        # Paying customers
        paying = db.query(func.count(User.id)).filter(
            User.plan != "free"
        ).scalar() or 0

        # Total requests today
        req_count = db.query(func.count(UsageRecord.id)).filter(
            UsageRecord.created_at >= day_start
        ).scalar() or 0

        subject = f"💰 KopyKat Daily Report — ${today_rev/100:.2f} earned today"
        body = f"""
        <html><body style="font-family: Arial; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color:#6c63ff;">📊 Daily Revenue Report</h2>
        <p style="color:#666;">{now.strftime('%B %d, %Y')}</p>

        <table style="width:100%; border-collapse:collapse; margin:20px 0;">
          <tr style="background:#6c63ff; color:white;">
            <th style="padding:12px; text-align:left;">Metric</th>
            <th style="padding:12px; text-align:right;">Value</th>
          </tr>
          <tr style="background:#f9f9f9;">
            <td style="padding:12px;">💵 Revenue Today</td>
            <td style="padding:12px; text-align:right; font-weight:bold;">${today_rev/100:.2f}</td>
          </tr>
          <tr>
            <td style="padding:12px;">📅 Revenue This Month</td>
            <td style="padding:12px; text-align:right; font-weight:bold;">${month_rev/100:.2f}</td>
          </tr>
          <tr style="background:#f9f9f9;">
            <td style="padding:12px;">👥 New Signups Today</td>
            <td style="padding:12px; text-align:right;">{new_users}</td>
          </tr>
          <tr>
            <td style="padding:12px;">💳 Paying Customers</td>
            <td style="padding:12px; text-align:right;">{paying}</td>
          </tr>
          <tr style="background:#f9f9f9;">
            <td style="padding:12px;">🤖 API Requests Today</td>
            <td style="padding:12px; text-align:right;">{req_count:,}</td>
          </tr>
        </table>

        <p style="color:#999; font-size:12px;">
          This report is auto-generated by KopyKat. Check your 
          <a href="https://dashboard.stripe.com/payouts">Stripe dashboard</a> for payout status.
        </p>
        </body></html>
        """
        _send_email(subject, body, OWNER_EMAIL)

    except Exception as e:
        logger.error(f"Daily report failed: {e}")
    finally:
        db.close()


def _cleanup_old_usage_records():
    """
    Purges usage records older than 90 days to keep the DB lean.
    Runs weekly on Sunday at 3am UTC.
    """
    db: Session = SessionLocal()
    try:
        cutoff  = datetime.utcnow() - timedelta(days=90)
        deleted = db.query(UsageRecord).filter(UsageRecord.created_at < cutoff).delete()
        db.commit()
        if deleted:
            logger.info(f"Cleaned up {deleted} old usage records")
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        db.rollback()
    finally:
        db.close()


def _check_subscription_health():
    """
    Finds users with past_due subscriptions older than 7 days and suspends them.
    Runs daily. Stripe handles most of this via webhooks but this is a safety net.
    """
    db: Session = SessionLocal()
    try:
        from .database import Subscription
        grace_cutoff = datetime.utcnow() - timedelta(days=7)

        past_due_subs = db.query(Subscription).filter(
            Subscription.status == "past_due",
            Subscription.current_period_end < grace_cutoff,
        ).all()

        for sub in past_due_subs:
            user = db.query(User).filter(User.id == sub.user_id).first()
            if user and user.plan != "free":
                user.plan                  = "free"
                user.generations_remaining = 0
                logger.info(f"Suspended past-due account: {user.email}")

        db.commit()
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        db.rollback()
    finally:
        db.close()


# ── Scheduler setup ───────────────────────────────────────────────────────────

def create_scheduler() -> AsyncIOScheduler:
    """Creates and configures the background scheduler. Called on startup."""
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Reset daily API counters — every day at midnight UTC
    scheduler.add_job(
        _reset_daily_api_counters,
        CronTrigger(hour=0, minute=0),
        id="reset_daily_counters",
        replace_existing=True,
    )

    # Daily revenue report email — every day at 8am UTC
    scheduler.add_job(
        _send_daily_revenue_report,
        CronTrigger(hour=8, minute=0),
        id="daily_revenue_report",
        replace_existing=True,
    )

    # Cleanup old records — every Sunday at 3am UTC
    scheduler.add_job(
        _cleanup_old_usage_records,
        CronTrigger(day_of_week="sun", hour=3, minute=0),
        id="weekly_cleanup",
        replace_existing=True,
    )

    # Subscription health check — every day at 2am UTC
    scheduler.add_job(
        _check_subscription_health,
        CronTrigger(hour=2, minute=0),
        id="subscription_health",
        replace_existing=True,
    )
    
    # ── Marketing Engine Jobs ─────────────────────────────────────────────────
    from .marketing import generate_seo_post, run_drip_campaigns, scan_reddit_opportunities

    # Publish a new SEO blog post every Monday, Wednesday, Friday at 14:00 UTC
    scheduler.add_job(
        generate_seo_post,
        CronTrigger(day_of_week="mon,wed,fri", hour=14, minute=0),
        id="seo_blog_engine",
        replace_existing=True,
    )

    # Run email drip campaigns every day at 10:00 UTC
    scheduler.add_job(
        run_drip_campaigns,
        CronTrigger(hour=10, minute=0),
        id="email_drip_bot",
        replace_existing=True,
    )

    # Scan for opportunities (leads) every 4 hours
    scheduler.add_job(
        scan_reddit_opportunities,
        CronTrigger(hour="*/4", minute=15),
        id="opportunity_scout",
        replace_existing=True,
    )

    logger.info("Background scheduler configured with 7 automated tasks (including marketing)")
    return scheduler

def _send_password_reset_email(email: str, token: str, base_url: str):
    subject = "Reset Your Password - KopyKat"
    reset_link = f"{base_url}/auth/reset-password?token={token}"
    body = f"Hi,<br><br>You requested a password reset. Click the link below to set a new password:<br><br><a href='{reset_link}'>{reset_link}</a><br><br>If you did not request this, please ignore this email."
    _send_email(subject, body, email)

def _send_verification_email(email: str, token: str, base_url: str):
    subject = "Verify Your Email - KopyKat"
    verify_link = f"{base_url}/auth/verify-email?token={token}"
    body = f"Welcome to KopyKat!<br><br>Please verify your email address by clicking the link below:<br><br><a href='{verify_link}'>{verify_link}</a>"
    _send_email(subject, body, email)
