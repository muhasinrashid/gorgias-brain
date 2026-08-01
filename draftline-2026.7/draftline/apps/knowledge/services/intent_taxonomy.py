"""Seed and manage intent taxonomy for Curated / ResolutionPair labeling."""

from __future__ import annotations

from apps.knowledge.models import IntentNode, Source, SourceType

# PRODUCT_SPEC M2 seed — Help Center top-level + common leaves + NOT_SUPPORT
DEFAULT_TAXONOMY: list[tuple[str, str, str | None]] = [
    ("support", "Support", None),
    ("order_status", "Order status", "support"),
    ("order_status.delivered_not_received", "Delivered not received", "order_status"),
    ("order_status.no_order_found", "No order found", "order_status"),
    ("order_change", "Order change and cancellation", "support"),
    ("returns", "Returns and exchanges", "support"),
    ("returns.partial_refund", "Partial refunds", "returns"),
    ("vat_duties", "VAT and duties", "support"),
    ("shipping", "Shipping", "support"),
    ("payment", "Payment", "support"),
    ("repair_service", "Repair and service", "support"),
    ("warranty", "Warranty", "support"),
    ("magnetism", "Magnetism", "support"),
    ("strap_compatibility", "Strap compatibility", "support"),
    ("gift_options", "Gift options", "support"),
    ("technical", "Technical questions", "support"),
    ("not_support", "NOT_SUPPORT", None),
    ("not_support.spam", "Spam", "not_support"),
    ("not_support.sales", "Sales / wholesale", "not_support"),
    ("not_support.other", "Other non-support", "not_support"),
]


def seed_intent_taxonomy(team, *, include_macros: bool = True, include_web_titles: bool = True) -> dict:
    created = 0
    updated = 0
    by_slug: dict[str, IntentNode] = {}

    for slug, label, parent_slug in DEFAULT_TAXONOMY:
        parent = by_slug.get(parent_slug) if parent_slug else None
        node, was_created = IntentNode.objects.update_or_create(
            team=team,
            slug=slug,
            defaults={
                "label": label,
                "parent": parent,
                "source": "seed",
                "is_active": True,
            },
        )
        by_slug[slug] = node
        created += int(was_created)
        updated += int(not was_created)

    macro_added = 0
    if include_macros:
        for title in (
            Source.objects.filter(team=team, source_type=SourceType.MACRO, is_active=True)
            .exclude(title="")
            .values_list("title", flat=True)
            .distinct()[:200]
        ):
            slug = _slugify(f"macro.{title}")[:120]
            _, was_created = IntentNode.objects.get_or_create(
                team=team,
                slug=slug,
                defaults={
                    "label": title[:255],
                    "parent": by_slug.get("support"),
                    "source": "macro",
                    "is_active": True,
                },
            )
            macro_added += int(was_created)

    web_added = 0
    if include_web_titles:
        for title in (
            Source.objects.filter(team=team, source_type=SourceType.WEB_PAGE, is_active=True)
            .exclude(title="")
            .values_list("title", flat=True)
            .distinct()[:80]
        ):
            # Category hubs become top leaves under support
            if title.lower() in {"reef", "home", "search", "login"}:
                continue
            slug = _slugify(f"hc.{title}")[:120]
            _, was_created = IntentNode.objects.get_or_create(
                team=team,
                slug=slug,
                defaults={
                    "label": title[:255],
                    "parent": by_slug.get("support"),
                    "source": "hc",
                    "is_active": True,
                },
            )
            web_added += int(was_created)

    return {
        "seed_upserted": created + updated,
        "seed_created": created,
        "macros_added": macro_added,
        "web_added": web_added,
        "total": IntentNode.objects.filter(team=team).count(),
    }


def _slugify(value: str) -> str:
    import re

    s = (value or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", ".", s)
    return s.strip(".") or "untitled"
