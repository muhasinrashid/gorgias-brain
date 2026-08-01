"""Ticket qualification — precision over recall.

Only SUPPORT should feed knowledge / drafting. When unsure, leave UNCLEAR.
Version this module carefully; re-runs update qualifier_version on each ticket.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from apps.tickets.models import Qualification

QUALIFIER_VERSION = "rules-v2"
HYBRID_QUALIFIER_VERSION = "hybrid-v1"

# High-precision non-support patterns (checked before SUPPORT heuristics).
_SOCIAL = [
    re.compile(r"(?i)^mention in .+['’]s story"),
    re.compile(r"(?i)^mention in .+ story"),
    re.compile(r"(?i)message restriction activity"),
    re.compile(r"(?i)^new follower"),
    re.compile(r"(?i)^tagged in (a |an )?(photo|post|story)"),
]

_SYSTEM = [
    re.compile(r"(?i)^out of stock notification"),
    re.compile(r"(?i)^low inventory warning"),
    re.compile(r"(?i)^abwesend\b"),
    re.compile(r"(?i)^automatische antwort"),
    re.compile(r"(?i)automatische eingangsbestätigung"),
    re.compile(r"(?i)bitte nicht antworten"),
    re.compile(r"(?i)^google indexed post"),
    re.compile(r"(?i)you have authorized a payment"),
    re.compile(r"(?i)^case #\s*\d+\s*created"),
    re.compile(r"(?i)digitaler einlieferungsbeleg"),
    re.compile(r"(?i)abrechnungsbelege"),
    re.compile(r"(?i)^oo[o]?ut of office"),
    re.compile(r"(?i)^out of (the )?office"),
    re.compile(r"(?i)^auto[- ]?reply"),
    re.compile(r"(?i)^automatic reply"),
]

_VENDOR = [
    re.compile(r"(?i)manufacturing partner"),
    re.compile(r"(?i)jewelry packaging"),
    re.compile(r"(?i)packaging options for transport"),
    re.compile(r"(?i)brand ambassador"),
    re.compile(r"(?i)management software"),
    re.compile(r"(?i)openai ads"),
    re.compile(r"(?i)special offer on website"),
    re.compile(r"(?i)mobile app & software"),
    re.compile(r"(?i)yuyao|ruimei commodity"),
    re.compile(r"(?i)windup watch fair"),
    re.compile(r"(?i)last block of rooms"),
    re.compile(r"(?i)wholesale (partnership|inquiry|opportunity)"),
    re.compile(r"(?i)seo (services|package|agency)"),
    re.compile(r"(?i)influencer (collaboration|partnership)"),
]

_SPAM = [
    re.compile(r"(?i)ad account .+ (disabled|disabilit)"),
    re.compile(r"(?i)fanpage will be disabled"),
    re.compile(r"(?i)pagina fan verranno disattivati"),
    re.compile(r"(?i)copyright policy assessment"),
    re.compile(r"(?i)gift card.*(claim|verify|urgent)"),
    re.compile(r"(?i)verify your (paypal|account).*urgent"),
    re.compile(r"(?i)suspicious (login|activity).*(click|verify)"),
]

_MARKETING = [
    re.compile(r"(?i)^newsletter\b"),
    re.compile(r"(?i)^flash sale"),
    re.compile(r"(?i)^\d+%\s*off\b"),
]

_INTERNAL = [
    re.compile(r"(?i)^test\b"),
    re.compile(r"(?i)^\[internal\]"),
]

_SUPPORT = [
    re.compile(r"(?i)^product question\b"),
    re.compile(r"(?i)\border\b"),
    re.compile(r"(?i)\bcancel\b"),
    re.compile(r"(?i)\breturn\b"),
    re.compile(r"(?i)\brefund\b"),
    re.compile(r"(?i)\bwarrant"),
    re.compile(r"(?i)\brepair\b"),
    re.compile(r"(?i)\bbezel\b"),
    re.compile(r"(?i)\bstrap\b"),
    re.compile(r"(?i)\bbracelet\b"),
    re.compile(r"(?i)\bshipping\b"),
    re.compile(r"(?i)\btracking\b"),
    re.compile(r"(?i)\bdelivery\b"),
    re.compile(r"(?i)\bship\b"),
    re.compile(r"(?i)issues? with my watch"),
    re.compile(r"(?i)when will .+ (be )?back"),
    re.compile(r"(?i)\bis this available"),
    re.compile(r"(?i)\b(purchase|buying|bought)\b"),
    re.compile(r"(?i)\brotor\b"),
    re.compile(r"(?i)\b(kaufdatum|ausfall)\b"),
    re.compile(r"(?i)brauche noch hilfe"),
    re.compile(r"(?i)i have a question"),
    re.compile(r"(?i)need more help"),
    re.compile(r"(?i)direct message with "),
    re.compile(r"(?i)^conversation with "),
    re.compile(r"(?i)\b(essence|reef|stratos|field|aria)\b"),
]

_AUTORESPONDER = [
    re.compile(r"(?i)thank you for contacting us"),
    re.compile(r"(?i)we.?ve received your message"),
    re.compile(r"(?i)appreciate your interest"),
    re.compile(r"(?i)notre équipe vous recontactera"),
    re.compile(r"(?i)within \d+ business days"),
    re.compile(r"(?i)automatische (antwort|eingangsbestätigung)"),
    re.compile(r"(?i)out of (the )?office"),
    re.compile(r"(?i)abwesend"),
]


@dataclass(frozen=True)
class QualificationResult:
    qualification: str
    confidence: float
    reason: str
    version: str = QUALIFIER_VERSION


def qualify_ticket(
    *,
    subject: str,
    channel: str = "",
    customer_email: str = "",
    first_inbound_text: str = "",
) -> QualificationResult:
    """Rules-only classifier. Prefer false UNCLEAR over false SUPPORT."""
    return qualify_ticket_rules(
        subject=subject,
        channel=channel,
        customer_email=customer_email,
        first_inbound_text=first_inbound_text,
    )


def qualify_ticket_rules(
    *,
    subject: str,
    channel: str = "",
    customer_email: str = "",
    first_inbound_text: str = "",
) -> QualificationResult:
    """Classify a ticket with regex rules only."""
    subject = (subject or "").strip()
    blob = f"{subject}\n{first_inbound_text or ''}".strip()
    channel_l = (channel or "").lower()

    for rx in _SPAM:
        if rx.search(blob):
            return QualificationResult(Qualification.SPAM_PHISHING, 0.92, f"spam:{rx.pattern}")

    for rx in _SOCIAL:
        if rx.search(subject):
            return QualificationResult(Qualification.SOCIAL_NOTIFICATION, 0.95, f"social:{rx.pattern}")

    if channel_l in {"instagram-mention", "facebook-mention", "twitter"}:
        return QualificationResult(Qualification.SOCIAL_NOTIFICATION, 0.9, f"channel:{channel_l}")

    for rx in _SYSTEM:
        if rx.search(blob):
            return QualificationResult(Qualification.SYSTEM_NOTIFICATION, 0.93, f"system:{rx.pattern}")

    for rx in _VENDOR:
        if rx.search(blob):
            return QualificationResult(Qualification.VENDOR_PITCH, 0.9, f"vendor:{rx.pattern}")

    for rx in _INTERNAL:
        if rx.search(subject):
            return QualificationResult(Qualification.INTERNAL, 0.8, f"internal:{rx.pattern}")

    for rx in _MARKETING:
        if rx.search(subject):
            return QualificationResult(Qualification.MARKETING_INBOUND, 0.85, f"marketing:{rx.pattern}")

    # Help-center product questions are usually real support.
    if channel_l == "help-center" and re.search(r"(?i)product question", subject):
        return QualificationResult(Qualification.SUPPORT, 0.9, "help-center-product-question")

    for rx in _SUPPORT:
        if rx.search(blob):
            return QualificationResult(Qualification.SUPPORT, 0.82, f"support:{rx.pattern}")

    return QualificationResult(Qualification.UNCLEAR, 0.3, "no-rule-matched")


def qualify_ticket_hybrid(
    *,
    subject: str,
    channel: str = "",
    customer_email: str = "",
    first_inbound_text: str = "",
) -> QualificationResult:
    """Rules first; LLM only when rules return UNCLEAR (or low-confidence SUPPORT)."""
    rules = qualify_ticket_rules(
        subject=subject,
        channel=channel,
        customer_email=customer_email,
        first_inbound_text=first_inbound_text,
    )
    # High-precision non-support from rules — trust them.
    if rules.qualification != Qualification.UNCLEAR and rules.qualification != Qualification.SUPPORT:
        return QualificationResult(rules.qualification, rules.confidence, rules.reason, HYBRID_QUALIFIER_VERSION)

    # Strong rule SUPPORT (≥0.88) — skip LLM.
    if rules.qualification == Qualification.SUPPORT and rules.confidence >= 0.88:
        return QualificationResult(rules.qualification, rules.confidence, rules.reason, HYBRID_QUALIFIER_VERSION)

    from apps.tickets.services.llm_qualification import llm_qualify_ticket

    llm = llm_qualify_ticket(
        subject=subject,
        channel=channel,
        customer_email=customer_email,
        first_inbound_text=first_inbound_text,
    )
    # Prefer LLM when it is decisive; otherwise keep rules SUPPORT if present.
    if llm.qualification != Qualification.UNCLEAR:
        return QualificationResult(
            llm.qualification,
            llm.confidence,
            f"hybrid(rules={rules.reason}|{llm.reason})",
            HYBRID_QUALIFIER_VERSION,
        )
    if rules.qualification == Qualification.SUPPORT:
        return QualificationResult(rules.qualification, rules.confidence, rules.reason, HYBRID_QUALIFIER_VERSION)
    return QualificationResult(
        Qualification.UNCLEAR,
        llm.confidence,
        f"hybrid(rules={rules.reason}|{llm.reason})",
        HYBRID_QUALIFIER_VERSION,
    )


def apply_qualification_to_ticket(ticket, *, backend: str = "rules") -> QualificationResult:
    first_inbound = ""
    for msg in ticket.messages.filter(direction="INBOUND").order_by("sequence")[:1]:
        first_inbound = msg.normalised_text or msg.raw_body_text or ""
        break

    kwargs = {
        "subject": ticket.subject,
        "channel": ticket.channel,
        "customer_email": ticket.customer_email,
        "first_inbound_text": first_inbound,
    }
    if backend == "hybrid":
        result = qualify_ticket_hybrid(**kwargs)
    elif backend == "llm":
        from apps.tickets.services.llm_qualification import llm_qualify_ticket

        result = llm_qualify_ticket(**kwargs)
    else:
        result = qualify_ticket_rules(**kwargs)

    ticket.qualification = result.qualification
    ticket.qualification_confidence = result.confidence
    ticket.qualifier_version = result.version
    ticket.save(update_fields=["qualification", "qualification_confidence", "qualifier_version", "updated_at"])
    return result


def is_autoresponder_text(text: str) -> bool:
    if not text or len(text.strip()) < 20:
        return False
    return any(rx.search(text) for rx in _AUTORESPONDER)


def flag_autoresponder_messages(ticket) -> int:
    updated = 0
    for msg in ticket.messages.filter(author_type="AGENT"):
        text = msg.normalised_text or msg.raw_body_text or ""
        flag = is_autoresponder_text(text)
        if msg.is_autoresponder != flag or msg.classifier_version != QUALIFIER_VERSION:
            msg.is_autoresponder = flag
            msg.classifier_version = QUALIFIER_VERSION
            msg.save(update_fields=["is_autoresponder", "classifier_version", "updated_at"])
            updated += 1
    return updated
