"""
content_governance.py — Content safety, anti-defamation, and brand compliance guardrails.
Ensures generated marketing copy, competitor counter-angles, and SEO articles comply with commercial advertising standards.
"""

import re
import logging
from typing import Tuple, List

logger = logging.getLogger(__name__)

# Banned / Defamatory patterns that must never appear in generated copy
DEFAMATORY_PATTERNS = [
    r"\b(scam|fraud|criminal|illegal|counterfeit|stolen|corrupt|cheaters|fake company)\b",
    r"\b(lawsuit|sued|felony|guilty of crime)\b",
]

def audit_generated_content(text: str, context: str = "") -> Tuple[bool, List[str], str]:
    """
    Audits generated copy for defamatory statements or false comparative claims.
    Returns: (is_safe: bool, flagged_reasons: List[str], cleaned_text: str)
    """
    if not text:
        return True, [], text

    flagged = []
    cleaned_text = text

    # 1. Defamation / malicious allegation check
    for pattern in DEFAMATORY_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            flagged.append(f"Contains potentially defamatory claim: '{matches[0]}'")
            # Sanitize by replacing with neutral phrasing
            cleaned_text = re.sub(pattern, "competitor product limitations", cleaned_text, flags=re.IGNORECASE)

    # 2. Check for absolute unsubstantiated medical or guarantee claims
    unsubstantiated_claims = [
        r"\b100% cure\b",
        r"\bguaranteed to make you rich\b",
        r"\b100% risk free investment\b"
    ]
    for claim in unsubstantiated_claims:
        if re.search(claim, text, re.IGNORECASE):
            flagged.append(f"Unsubstantiated absolute claim flagged: '{claim}'")
            cleaned_text = re.sub(claim, "tested quality assurance", cleaned_text, flags=re.IGNORECASE)

    if flagged:
        logger.warning("Content governance modified generated copy: %s", flagged)

    return len(flagged) == 0, flagged, cleaned_text
