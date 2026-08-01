"""Quarantine crawled pages that are not knowledge (PDP/collections dumps).

Legal pages (terms/privacy) stay active but are tagged for ranking penalties —
they often hold warranty/shipping facts when FAQ articles are missing.
"""

from __future__ import annotations

import re

from apps.knowledge.models import Source, SourceType

_KEEP = re.compile(r"/faqs?/|hcUrl=|/help(?:-center)?/|/articles?/", re.I)
_LEGAL = re.compile(r"/terms|/privacy", re.I)
_DROP = re.compile(
    r"/login|/search|/collections?/|/cart|/checkout|/products?/|"
    r"/accessories/|/formex-world|/our-story|/watches/?$",
    re.I,
)


def classify_web_page(url: str, title: str, content: str) -> str:
    """Return keep | legal | drop."""
    url = url or ""
    title = (title or "").strip()
    if _KEEP.search(url):
        return "keep"
    if _LEGAL.search(url):
        return "legal"
    if _DROP.search(url):
        return "drop"
    if re.fullmatch(r"https?://[^/]+/?", url):
        return "drop"
    if title.upper() in {"REEF", "HOME", "SEARCH", "LOGIN"} and not _KEEP.search(url):
        return "drop"
    if len((content or "").strip()) < 200 and not _KEEP.search(url):
        return "drop"
    return "keep"


def quarantine_noisy_web_sources(team) -> dict:
    qs = Source.objects.filter(team=team, source_type=SourceType.WEB_PAGE)
    kept = 0
    legal = 0
    quarantined = 0
    for source in qs.iterator():
        tier = classify_web_page(source.url, source.title, source.normalised_content or source.raw_content)
        meta = dict(source.metadata or {})
        if tier == "keep":
            meta.pop("quarantined", None)
            meta.pop("noise_tier", None)
            source.is_active = True
            source.metadata = meta
            source.save(update_fields=["is_active", "metadata", "updated_at"])
            kept += 1
        elif tier == "legal":
            meta.pop("quarantined", None)
            meta["noise_tier"] = "legal"
            source.is_active = True
            source.metadata = meta
            source.save(update_fields=["is_active", "metadata", "updated_at"])
            legal += 1
        else:
            meta["quarantined"] = True
            meta["quarantine_reason"] = "non_knowledge_web_page"
            meta["noise_tier"] = "drop"
            source.is_active = False
            source.metadata = meta
            source.save(update_fields=["is_active", "metadata", "updated_at"])
            quarantined += 1
    return {"kept_active": kept, "legal_active": legal, "quarantined": quarantined}
