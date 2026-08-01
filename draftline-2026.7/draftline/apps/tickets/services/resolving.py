"""Identify resolving replies and autoresponders on ticket threads.

Heuristic (v1): among non-autoresponder agent OUTBOUND messages, mark the last
substantial one as resolving when the ticket is closed. Multi-agent threads may
have earlier partial answers — we keep a single primary resolving flag for M1
metrics and refine later.
"""

from __future__ import annotations

import re

from apps.tickets.models import AuthorType, MessageDirection, Ticket, TicketMessage
from apps.tickets.services.qualification import is_autoresponder_text

RESOLVING_CLASSIFIER_VERSION = "resolving-v1"

_SUBSTANTIAL_MIN = 40


def _is_substantial(text: str) -> bool:
    return len((text or "").strip()) >= _SUBSTANTIAL_MIN


def annotate_thread_messages(ticket: Ticket) -> dict[str, int]:
    """Update is_autoresponder / is_resolving_reply for all messages on a ticket."""
    messages = list(ticket.messages.order_by("sequence", "sent_at", "id"))
    autoresponder_count = 0
    for msg in messages:
        text = msg.normalised_text or msg.raw_body_text or ""
        is_auto = msg.author_type == AuthorType.AGENT and is_autoresponder_text(text)
        # Extra: very short agent acks
        if msg.author_type == AuthorType.AGENT and not is_auto:
            if re.fullmatch(r"(?is)\s*(thanks!?|thank you!?|ok\.?|okay\.?)\s*", text or ""):
                is_auto = True
        if msg.is_autoresponder != is_auto or msg.classifier_version != RESOLVING_CLASSIFIER_VERSION:
            msg.is_autoresponder = is_auto
            # don't wipe qualification classifier version if set to rules/hybrid — store resolving version
            # only when we own the field; keep both concerns on classifier_version for M1 simplicity
            msg.classifier_version = RESOLVING_CLASSIFIER_VERSION
            msg.save(update_fields=["is_autoresponder", "classifier_version", "updated_at"])
        if is_auto:
            autoresponder_count += 1

    # Clear previous resolving flags
    TicketMessage.objects.filter(ticket=ticket, is_resolving_reply=True).update(is_resolving_reply=False)

    candidates = [
        m
        for m in messages
        if m.author_type == AuthorType.AGENT
        and m.direction == MessageDirection.OUTBOUND
        and not m.is_autoresponder
        and _is_substantial(m.normalised_text or m.raw_body_text or "")
    ]

    resolving_count = 0
    if candidates and (ticket.status or "").lower() == "closed":
        winner = candidates[-1]
        winner.is_resolving_reply = True
        winner.classifier_version = RESOLVING_CLASSIFIER_VERSION
        winner.save(update_fields=["is_resolving_reply", "classifier_version", "updated_at"])
        resolving_count = 1

    return {"autoresponders": autoresponder_count, "resolving": resolving_count}
