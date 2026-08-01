"""Extract ResolutionPairs from SUPPORT tickets with resolving replies."""

from __future__ import annotations

import logging

from apps.knowledge.models import ResolutionPair
from apps.tickets.models import AuthorType, MessageDirection, Qualification, Ticket, TicketMessage

logger = logging.getLogger(__name__)

MIN_SUPPORT_CONFIDENCE = 0.8
MIN_QUESTION_CHARS = 20
MIN_RESOLUTION_CHARS = 40


def _customer_question(messages: list[TicketMessage], before: TicketMessage) -> str:
    prior = [
        m
        for m in messages
        if m.id < before.id
        and m.author_type == AuthorType.CUSTOMER
        and m.direction == MessageDirection.INBOUND
    ]
    if not prior:
        return ""
    text = (prior[-1].normalised_text or prior[-1].raw_body_text or "").strip()
    return text


def extract_pair_from_ticket(ticket: Ticket) -> ResolutionPair | None:
    """Create or update one ResolutionPair for a ticket's resolving reply."""
    if ticket.qualification != Qualification.SUPPORT:
        return None
    conf = ticket.qualification_confidence
    if conf is not None and conf < MIN_SUPPORT_CONFIDENCE:
        return None

    messages = list(ticket.messages.order_by("sequence", "sent_at", "id"))
    resolving = next((m for m in messages if m.is_resolving_reply and not m.is_autoresponder), None)
    if not resolving:
        return None

    resolution = (resolving.normalised_text or resolving.raw_body_text or "").strip()
    if len(resolution) < MIN_RESOLUTION_CHARS:
        return None

    question = _customer_question(messages, resolving)
    if len(question) < MIN_QUESTION_CHARS:
        question = (ticket.subject or "").strip()
    if len(question) < MIN_QUESTION_CHARS:
        return None

    context_bits = []
    if ticket.subject:
        context_bits.append(f"Subject: {ticket.subject}")
    if ticket.intent:
        context_bits.append(f"Intent: {ticket.intent}")

    quality = 0.5
    if conf is not None:
        quality = min(1.0, 0.4 + 0.6 * float(conf))
    if len(resolution) > 200:
        quality = min(1.0, quality + 0.1)

    existing = ResolutionPair.objects.filter(
        team=ticket.team, source_ticket_ids=[ticket.external_id]
    ).first()
    defaults = {
        "question_text": question[:8000],
        "context_summary": " · ".join(context_bits)[:2000],
        "resolution_text": resolution[:8000],
        "intent": (ticket.intent or "")[:128],
        "language": (ticket.language or "")[:16],
        "quality_score": quality,
        "is_exemplar": quality >= 0.85,
    }
    if existing:
        text_changed = (
            existing.question_text != defaults["question_text"]
            or existing.resolution_text != defaults["resolution_text"]
        )
        for key, value in defaults.items():
            setattr(existing, key, value)
        if text_changed:
            existing.embedding = None
            existing.embedder_version = ""
        existing.save()
        return existing
    return ResolutionPair.objects.create(
        team=ticket.team,
        source_ticket_ids=[ticket.external_id],
        **defaults,
    )


def extract_resolution_pairs_for_team(
    team,
    *,
    limit: int = 0,
    min_confidence: float = MIN_SUPPORT_CONFIDENCE,
) -> dict:
    qs = (
        Ticket.objects.filter(
            team=team,
            qualification=Qualification.SUPPORT,
            messages__is_resolving_reply=True,
        )
        .distinct()
        .order_by("-id")
    )
    if min_confidence > 0:
        # Keep null confidence (rules path may omit) OR high confidence
        from django.db.models import Q

        qs = qs.filter(Q(qualification_confidence__isnull=True) | Q(qualification_confidence__gte=min_confidence))
    if limit:
        qs = qs[:limit]

    created = 0
    skipped = 0
    for ticket in qs.iterator():
        pair = extract_pair_from_ticket(ticket)
        if pair:
            created += 1
        else:
            skipped += 1
    return {"pairs": created, "skipped": skipped}
