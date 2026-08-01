"""Ticket / message body normalisation.

talon is preferred for quote/signature stripping when installed; otherwise a
minimal HTML strip is used so M1 can proceed without blocking on deps.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup


def html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def strip_quotes_and_signatures(text: str) -> str:
    if not text:
        return ""
    try:
        from talon import quotations, signature

        text = quotations.extract_from(text, "text/plain")
        text = signature.extract(text, sender="")[0] or text
    except Exception:
        # Fallback: cut at common English reply markers
        markers = [
            r"(?m)^On .+ wrote:$",
            r"(?m)^From:\s+.+$",
            r"(?m)^-{2,}\s*$",
            r"(?m)^Sent from my .+$",
        ]
        for marker in markers:
            parts = re.split(marker, text, maxsplit=1)
            if len(parts) > 1:
                text = parts[0]
                break
    return text.strip()


def normalise_message_body(*, body_html: str = "", body_text: str = "") -> str:
    raw = (body_text or "").strip() or html_to_text(body_html)
    return strip_quotes_and_signatures(raw)


def classify_author(raw_message: dict) -> tuple[str, str]:
    """Return (AuthorType, MessageDirection). Prefer from_agent — see EXTERNAL_API_NOTES."""
    from apps.tickets.models import AuthorType, MessageDirection

    channel = (raw_message.get("channel") or "").lower()
    if channel == "internal-note":
        return AuthorType.AGENT, MessageDirection.INTERNAL_NOTE

    from_agent = raw_message.get("from_agent")
    if from_agent is True:
        return AuthorType.AGENT, MessageDirection.OUTBOUND
    if from_agent is False:
        return AuthorType.CUSTOMER, MessageDirection.INBOUND

    sender = raw_message.get("sender") or {}
    sender_type = (sender.get("type") or "").lower()
    if sender_type in {"agent", "user"}:
        return AuthorType.AGENT, MessageDirection.OUTBOUND
    if sender_type in {"customer", "visitor"}:
        return AuthorType.CUSTOMER, MessageDirection.INBOUND

    return AuthorType.SYSTEM, MessageDirection.INBOUND
