"""
reviews_ugc.py — Post-Purchase Review & UGC Drip Generator for KopyKat.
Generates automated customer nurture sequences and classifies incoming customer reviews
with sentiment tagging and automated merchant resolution responses.
"""

import json
import logging
import uuid
from typing import Dict, Any

logger = logging.getLogger(__name__)


def generate_post_purchase_drip(product_name: str, brand_tone: str = "Warm and helpful", incentive: str = "15% off your next order") -> list:
    """
    Generates a 3-step post-purchase review request and UGC sequence.
    """
    clean_prod = product_name.strip()
    return [
        {
            "step": 1,
            "day": 3,
            "goal": "Delivery Check & Onboarding",
            "subject": f"How is your new {clean_prod} treating you?",
            "body": f"Hi there,\n\nWe wanted to make sure your {clean_prod} arrived safely and that you're enjoying the unboxing experience!\n\nHere are a few quick tips to get the absolute most out of it:\n1. Check the setup guide enclosed in your package.\n2. If you have any questions at all, reply directly to this email.\n\nEnjoy your new {clean_prod}!\n\nBest regards,\nThe Team"
        },
        {
            "step": 2,
            "day": 7,
            "goal": "Review & Photo UGC Request",
            "subject": f"Quick favor (plus {incentive} inside)",
            "body": f"Hi there,\n\nNow that you have had a week to test drive your {clean_prod}, we would love to hear your honest feedback.\n\nCould you take 30 seconds to share your experience? If you snap a quick photo or video with your review, we will instantly email you a coupon for {incentive} on your next order.\n\nClick here to leave your review and claim your reward!\n\nThank you for being part of our community,\nThe Team"
        },
        {
            "step": 3,
            "day": 14,
            "goal": "VIP Loyalty & Replenishment",
            "subject": f"VIP Perk: An exclusive reward for you and a friend",
            "body": f"Hi there,\n\nWe hope your {clean_prod} has become an indispensable part of your routine!\n\nAs a valued customer, we wanted to give you an exclusive VIP pass. Share your custom referral link with a friend and you will both receive a bonus reward on your next order.\n\nThank you for choosing us,\nThe Team"
        }
    ]


def classify_review_sentiment_and_reply(customer_name: str, product_name: str, rating: int, review_text: str) -> Dict[str, Any]:
    """
    Classifies review sentiment and crafts an automated draft reply for the merchant.
    """
    lower_text = review_text.lower()
    negative_signals = ["broken", "terrible", "worst", "waste", "disappointed", "refund", "never", "hate", "awful", "scam", "poor"]
    positive_signals = ["love", "great", "excellent", "perfect", "amazing", "best", "high quality", "fast", "awesome", "recommend"]

    neg_count = sum(1 for s in negative_signals if s in lower_text)
    pos_count = sum(1 for s in positive_signals if s in lower_text)

    if rating <= 2 or neg_count > pos_count:
        sentiment = "negative"
        status = "action_needed"
        draft_reply = (
            f"Dear {customer_name},\n\n"
            f"Thank you for sharing your feedback regarding your {product_name}. We are truly sorry to hear that your experience "
            f"did not meet expectations. We take quality very seriously and would love the opportunity to make this right immediately.\n\n"
            f"Please reply directly to this email or contact our VIP support line, and we will arrange a replacement or full refund right away.\n\n"
            f"Sincerely,\nCustomer Experience Leadership"
        )
    elif rating == 3:
        sentiment = "neutral"
        status = "action_needed"
        draft_reply = (
            f"Hi {customer_name},\n\n"
            f"Thank you for reviewing your {product_name}. We appreciate your honest thoughts and are always striving to improve.\n\n"
            f"If there are specific features or adjustments you would love to see in future updates, please feel free to let us know!\n\n"
            f"Best regards,\nThe Team"
        )
    else:
        sentiment = "positive"
        status = "published"
        draft_reply = (
            f"Hi {customer_name}!\n\n"
            f"Thank you so much for the glowing review of your {product_name}! We are thrilled that you are enjoying it.\n\n"
            f"Your support means the world to our team. Enjoy your reward coupon on your next order!\n\n"
            f"Warmly,\nThe Team"
        )

    return {
        "sentiment": sentiment,
        "status": status,
        "draft_reply": draft_reply
    }
