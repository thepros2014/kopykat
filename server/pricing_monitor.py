"""
pricing_monitor.py — Automated Price & Margin Monitor for KopyKat.
Calculates real-time unit economics, margin health, and AI pricing recommendations
against competitor benchmarks.
"""

from typing import Optional, Dict, Any


def compute_pricing_analysis(
    cogs: float,
    selling_price: float,
    competitor_price: Optional[float] = None,
    target_margin: float = 40.0
) -> Dict[str, Any]:
    """
    Computes unit economics, status health, and actionable pricing recommendations.
    """
    if selling_price <= 0:
        return {
            "current_margin_pct": 0.0,
            "profit_per_unit_usd": 0.0,
            "status": "critical",
            "recommendation": "CRITICAL: Selling price must be greater than zero."
        }

    profit_per_unit = round(selling_price - cogs, 2)
    current_margin_pct = round((profit_per_unit / selling_price) * 100, 2)

    # Required selling price to hit target margin: target_margin = (P - COGS)/P => P = COGS / (1 - target_margin/100)
    if target_margin < 100:
        target_price = round(cogs / (1 - (target_margin / 100)), 2)
    else:
        target_price = selling_price

    if current_margin_pct < 15.0:
        status = "critical"
        rec = f"CRITICAL: Profit margin is dangerously thin ({current_margin_pct}%). To achieve your {target_margin}% target margin, adjust price to ${target_price:.2f}."
    elif current_margin_pct < target_margin:
        status = "warning"
        rec = f"WARNING: Profit margin ({current_margin_pct}%) is below your {target_margin}% target. Recommended price is ${target_price:.2f} (+$ {round(target_price - selling_price, 2):.2f})."
    elif competitor_price and competitor_price > (selling_price * 1.12):
        status = "healthy"
        headroom_price = round(min(competitor_price * 0.95, selling_price * 1.15), 2)
        rec = f"OPPORTUNITY: Competitor is charging ${competitor_price:.2f}. You can safely increase price to ${headroom_price:.2f} to boost unit profit by ${round(headroom_price - selling_price, 2):.2f} while staying under competitor pricing."
    elif competitor_price and competitor_price < (selling_price * 0.85):
        status = "warning"
        rec = f"TACTICAL: Competitor is undercutting at ${competitor_price:.2f}. Do not trigger a price war; use Review Miner counter-copy and bundle bonuses to defend margin."
    else:
        status = "healthy"
        rec = f"HEALTHY: Delivering {current_margin_pct}% gross margin (${profit_per_unit:.2f}/unit) aligned with your target."

    return {
        "current_margin_pct": current_margin_pct,
        "profit_per_unit_usd": profit_per_unit,
        "status": status,
        "recommendation": rec
    }
