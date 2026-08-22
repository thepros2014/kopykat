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

from .database import SessionLocal, User, APIKey, UsageRecord, RevenueRecord, Subscription

logger = logging.getLogger(__name__)

OWNER_EMAIL = os.getenv("OWNER_EMAIL", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")


def _send_email(subject: str, body: str, to: str):
    """Send an email via SMTP. No-op when SMTP is not configured."""
    if not all([SMTP_USER, SMTP_PASSWORD]):
        logger.info("Email not configured — skipping notification")
        return
    if not to:
        logger.warning("Email destination missing — skipping notification")
        return
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("Email sent: %s", subject)
    except Exception as exc:
        logger.error("Email send failed: %s", exc)


def _reset_daily_api_counters():
    db: Session = SessionLocal()
    try:
        updated = db.query(APIKey).update({"requests_today": 0})
        db.commit()
        logger.info("Daily API counters reset for %s keys", updated)
    except Exception as exc:
        logger.error("Counter reset failed: %s", exc)
        db.rollback()
    finally:
        db.close()


def _send_daily_revenue_report():
    if not OWNER_EMAIL:
        return
    db: Session = SessionLocal()
    try:
        from sqlalchemy import func
        now = datetime.utcnow()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        today_rev = db.query(func.sum(RevenueRecord.amount_cents)).filter(
            RevenueRecord.status == "succeeded",
            RevenueRecord.created_at >= day_start,
        ).scalar() or 0
        month_rev = db.query(func.sum(RevenueRecord.amount_cents)).filter(
            RevenueRecord.status == "succeeded",
            RevenueRecord.created_at >= month_start,
        ).scalar() or 0
        new_users = db.query(func.count(User.id)).filter(User.created_at >= day_start).scalar() or 0
        paying = db.query(func.count(User.id)).filter(User.plan != "free").scalar() or 0
        req_count = db.query(func.count(UsageRecord.id)).filter(UsageRecord.created_at >= day_start).scalar() or 0
        subject = f"💰 KopyKat Daily Report — ${today_rev/100:.2f} earned today"
        body = f"""
        <html><body style="font-family:Arial;max-width:600px;margin:0 auto;padding:20px;">
        <h2>📊 Daily Revenue Report</h2><p>{now.strftime('%B %d, %Y')}</p>
        <table style="width:100%;border-collapse:collapse">
        <tr><td>Revenue Today</td><td>${today_rev/100:.2f}</td></tr>
        <tr><td>Revenue This Month</td><td>${month_rev/100:.2f}</td></tr>
        <tr><td>New Signups Today</td><td>{new_users}</td></tr>
        <tr><td>Paying Customers</td><td>{paying}</td></tr>
        <tr><td>API Requests Today</td><td>{req_count:,}</td></tr>
        </table></body></html>
        """
        _send_email(subject, body, OWNER_EMAIL)
    except Exception as exc:
        logger.error("Daily report failed: %s", exc)
    finally:
        db.close()


def _cleanup_old_usage_records():
    db: Session = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=90)
        deleted = db.query(UsageRecord).filter(UsageRecord.created_at < cutoff).delete()
        db.commit()
        if deleted:
            logger.info("Cleaned up %s old usage records", deleted)
    except Exception as exc:
        logger.error("Cleanup failed: %s", exc)
        db.rollback()
    finally:
        db.close()


def _check_subscription_health():
    """Suspend accounts whose subscription has remained past_due beyond the grace period."""
    db: Session = SessionLocal()
    try:
        grace_cutoff = datetime.utcnow() - timedelta(days=7)
        past_due_subs = db.query(Subscription).filter(
            Subscription.status == "past_due",
            Subscription.current_period_end < grace_cutoff,
        ).all()
        for sub in past_due_subs:
            user = db.query(User).filter(User.id == sub.user_id).first()
            if user and user.plan != "free":
                user.plan = "free"
                user.generations = 0
                user.monthly_limit = 5
                logger.info("Suspended past-due account: %s", user.email)
        db.commit()
    except Exception as exc:
        logger.error("Health check failed: %s", exc)
        db.rollback()
    finally:
        db.close()


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(_reset_daily_api_counters, CronTrigger(hour=0, minute=0), id="reset_daily_counters", replace_existing=True)
    scheduler.add_job(_send_daily_revenue_report, CronTrigger(hour=8, minute=0), id="daily_revenue_report", replace_existing=True)
    scheduler.add_job(_cleanup_old_usage_records, CronTrigger(day_of_week="sun", hour=3, minute=0), id="weekly_cleanup", replace_existing=True)
    scheduler.add_job(_check_subscription_health, CronTrigger(hour=2, minute=0), id="subscription_health", replace_existing=True)

    from .marketing import generate_seo_post, run_drip_campaigns, scan_reddit_opportunities
    scheduler.add_job(generate_seo_post, CronTrigger(day_of_week="mon,wed,fri", hour=14, minute=0), id="seo_blog_engine", replace_existing=True)
    scheduler.add_job(run_drip_campaigns, CronTrigger(hour=10, minute=0), id="email_drip_bot", replace_existing=True)
    scheduler.add_job(scan_reddit_opportunities, CronTrigger(hour="*/4", minute=15), id="opportunity_scout", replace_existing=True)

    logger.info("Background scheduler configured with 7 automated tasks (including marketing)")
    return scheduler


def _send_password_reset_email(email: str, token: str, base_url: str):
    reset_link = f"{base_url}/auth/reset-password?token={token}"
    _send_email("Reset Your Password - KopyKat", f"Hi,<br><br>You requested a password reset. <a href='{reset_link}'>Reset your password</a>.<br><br>If you did not request this, ignore this email.", email)


def _send_verification_email(email: str, token: str, base_url: str):
    verify_link = f"{base_url}/auth/verify-email?token={token}"
    _send_email("Verify Your Email - KopyKat", f"Welcome to KopyKat!<br><br><a href='{verify_link}'>Verify your email address</a>.", email)
