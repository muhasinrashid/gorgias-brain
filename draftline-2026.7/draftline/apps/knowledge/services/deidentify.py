"""De-identify curated answers before approval."""

from __future__ import annotations

import re

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}\b")
_ORDER = re.compile(r"\b(?:order|invoice|po)[#:\s-]*[A-Z0-9-]{5,}\b", re.I)
_TRACKING = re.compile(
    r"\b(?:1Z[A-Z0-9]{16}|tracking[#:\s-]*[A-Z0-9]{8,}|(?:UPS|FedEx|DHL|USPS)[#:\s-]*[A-Z0-9-]+)\b",
    re.I,
)
_ADDRESSISH = re.compile(r"\b\d{1,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+(?:St|Street|Ave|Avenue|Rd|Road|Blvd)\b")


def deidentify_text(text: str) -> str:
    out = text or ""
    out = _EMAIL.sub("[email]", out)
    out = _TRACKING.sub("[tracking]", out)
    out = _ORDER.sub("[order]", out)
    out = _ADDRESSISH.sub("[address]", out)
    out = _PHONE.sub("[phone]", out)
    return out


def still_contains_pii(text: str) -> list[str]:
    """Return human labels for residual PII patterns (empty = clean enough)."""
    issues = []
    if _EMAIL.search(text or ""):
        issues.append("email")
    if _TRACKING.search(text or ""):
        issues.append("tracking")
    if _ORDER.search(text or ""):
        issues.append("order_id")
    if _ADDRESSISH.search(text or ""):
        issues.append("address")
    # phones are noisy; only flag long digit runs that look like phone after other scrubbing
    if _PHONE.search(text or "") and re.search(r"\d{7,}", text or ""):
        issues.append("phone")
    return issues
