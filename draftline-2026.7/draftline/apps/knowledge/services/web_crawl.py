"""Website crawl — platform Apify actor + httpx fallback. No embeddings (M2)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Abandon a crawl rather than pinning a Celery worker indefinitely.
APIFY_RUN_TIMEOUT = timedelta(minutes=20)


@dataclass
class CrawledPage:
    url: str
    title: str
    content: str
    crawler: str
    metadata: dict


def _extract_domain(url: str) -> str:
    parsed = urlparse(url)
    return f".{parsed.netloc.lstrip('www.')}"


def build_glob_patterns(url: str) -> list[dict[str, str]]:
    """Stay under the seed path — do not open the whole origin (avoids PDP/legal dumps)."""
    parsed = urlparse(url)
    path = parsed.path or "/"
    # FAQ hubs often use ?hcUrl= — allow query variants under /faqs/
    if "/faqs" in path.lower():
        origin = f"{parsed.scheme}://{parsed.netloc}"
        return [
            {"glob": f"{origin}/faqs"},
            {"glob": f"{origin}/faqs/**"},
            {"glob": f"{origin}/faqs?*"},
        ]
    base = url.rstrip("/")
    return [
        {"glob": base},
        {"glob": f"{base}/**"},
        {"glob": f"{base}?*"},
    ]


def build_include_url_patterns(url: str) -> list[str]:
    return [p["glob"] for p in build_glob_patterns(url)]


def build_draftline_actor_input(
    start_urls: list[str],
    *,
    max_pages: int = 30,
    max_depth: int = 2,
) -> dict:
    """Input contract for the custom Draftline Apify actor."""
    patterns: list[str] = []
    for u in start_urls:
        patterns.extend(build_include_url_patterns(u))
    # dedupe preserving order
    seen: set[str] = set()
    unique_patterns = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            unique_patterns.append(p)
    return {
        "startUrls": [{"url": u} for u in start_urls],
        "maxCrawlDepth": max_depth,
        "maxCrawlPages": max_pages,
        "sameOriginOnly": True,
        "includeUrlPatterns": unique_patterns,
        "excludeUrlPatterns": [
            "**/collections/**",
            "**/products/**",
            "**/cart**",
            "**/checkout**",
            "**/login**",
            "**/search**",
            "**/accessories/**",
        ],
        "waitForSelector": "",
        "localeHint": "",
    }


def build_stock_website_content_crawler_input(
    start_urls: list[str],
    *,
    max_pages: int = 30,
    max_depth: int = 2,
) -> dict:
    """Compat input for apify/website-content-crawler until custom actor ships."""
    primary = start_urls[0] if start_urls else "https://example.com"
    domain = _extract_domain(primary)
    globs: list[dict[str, str]] = []
    for u in start_urls:
        globs.extend(build_glob_patterns(u))
    return {
        "startUrls": [{"url": u} for u in start_urls],
        "maxCrawlDepth": max_depth,
        "maxCrawlPages": max_pages,
        "saveHtml": False,
        "saveMarkdown": True,
        "useCanonicalUrl": True,
        "keepUrlFragment": True,
        "initialCookies": [
            {"name": "cookieconsent_status", "value": "dismiss", "domain": domain, "path": "/"},
            {"name": "cookie_consent", "value": "accepted", "domain": domain, "path": "/"},
        ],
        "clickElementsCssSelector": ", ".join(
            [
                "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
                "button[name='accept']",
                ".cookie-accept",
                ".accept-cookies",
                "#accept-cookies",
                ".gl-close-button",
                ".welcome-popup-close",
                "[data-testid='close-button']",
            ]
        ),
        "removeElementsCssSelector": ", ".join(
            [
                ".modal-backdrop",
                ".popup",
                ".modal",
                "#CybotCookiebotDialog",
                ".cookie-banner",
                ".global-e-popup-container",
                ".newsletter-popup",
            ]
        ),
        "globs": globs,
    }


def _resolve_crawler_config() -> tuple[str, str, bool]:
    """Return (api_key, actor_id, enabled)."""
    from apps.knowledge.models import PlatformCrawlerSettings

    solo = PlatformCrawlerSettings.get_solo()
    key = solo.get_apify_api_key() if solo.enabled else ""
    actor = solo.resolve_actor() if solo.enabled else ""
    return key, actor, bool(solo.enabled and key and actor)


def build_actor_run_input(start_urls: list[str], *, max_pages: int, max_depth: int, actor_id: str) -> dict:
    if "website-content-crawler" in (actor_id or ""):
        return build_stock_website_content_crawler_input(start_urls, max_pages=max_pages, max_depth=max_depth)
    return build_draftline_actor_input(start_urls, max_pages=max_pages, max_depth=max_depth)


def run_field(run, name: str) -> str:
    """Read a field from an Apify run.

    apify-client >= 3.1 returns pydantic models with snake_case attributes;
    older versions returned camelCase dicts.
    """
    if run is None:
        return ""
    if isinstance(run, dict):
        camel = name if "_" not in name else name.split("_")[0] + "".join(p.title() for p in name.split("_")[1:])
        return str(run.get(camel) or run.get(name) or "")
    return str(getattr(run, name, "") or "")


def _pages_from_dataset_items(items: list[dict], *, crawler: str, run_id: str = "") -> list[CrawledPage]:
    pages: list[CrawledPage] = []
    for item in items:
        url = str(item.get("url") or "")
        if not url:
            continue
        content = str(item.get("markdown") or item.get("text") or item.get("content") or "")
        if not content.strip():
            continue
        title = str(item.get("title") or (item.get("metadata") or {}).get("title") or url)
        pages.append(
            CrawledPage(
                url=url,
                title=title[:512],
                content=content,
                crawler=crawler,
                metadata={
                    "apify_run_id": run_id,
                    "language": item.get("language") or "",
                    "httpStatus": item.get("httpStatus"),
                    "raw_metadata": item.get("metadata") or {},
                },
            )
        )
    return pages


def crawl_with_apify(
    start_urls: list[str],
    *,
    max_pages: int = 30,
    max_depth: int = 2,
) -> list[CrawledPage]:
    api_key, actor_id, ready = _resolve_crawler_config()
    if not ready:
        return []

    try:
        from apify_client import ApifyClient
    except ImportError:
        logger.warning("apify-client not installed; skipping Apify crawl")
        return []

    client = ApifyClient(api_key)
    run_input = build_actor_run_input(start_urls, max_pages=max_pages, max_depth=max_depth, actor_id=actor_id)
    logger.info("Starting Apify actor=%s urls=%s", actor_id, len(start_urls))
    run = client.actor(actor_id).call(run_input=run_input, run_timeout=APIFY_RUN_TIMEOUT)
    if run is None:
        logger.warning("Apify actor %s returned no run", actor_id)
        return []
    run_id = run_field(run, "id")
    dataset_id = run_field(run, "default_dataset_id")
    status = run_field(run, "status")
    if not dataset_id:
        logger.warning("Apify run %s finished with status=%s and no dataset", run_id, status)
        return []
    items = list(client.dataset(dataset_id).iterate_items())
    return _pages_from_dataset_items(items, crawler="apify", run_id=run_id)


def crawl_url_httpx(url: str) -> CrawledPage | None:
    from bs4 import BeautifulSoup

    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("httpx crawl failed for %s: %s", url, exc)
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
        element.decompose()
    main_tag = soup.find("main") or soup.find("article") or soup.find("div", class_="content") or soup.body
    content = main_tag.get_text(separator="\n", strip=True) if main_tag else ""
    if not content.strip():
        return None
    title = soup.title.string.strip() if soup.title and soup.title.string else url
    return CrawledPage(url=url, title=title[:512], content=content, crawler="httpx", metadata={})


def crawl_urls(
    start_urls: list[str],
    *,
    max_pages: int | None = None,
    max_depth: int | None = None,
) -> list[CrawledPage]:
    from apps.knowledge.models import PlatformCrawlerSettings

    solo = PlatformCrawlerSettings.get_solo()
    max_pages = max_pages if max_pages is not None else solo.default_max_pages
    max_depth = max_depth if max_depth is not None else solo.default_max_depth
    max_pages = min(int(max_pages), int(solo.hard_max_pages))
    max_depth = max(0, int(max_depth))
    urls = [u.strip() for u in start_urls if u and u.strip()]
    if not urls:
        return []

    pages = crawl_with_apify(urls, max_pages=max_pages, max_depth=max_depth)
    if pages:
        return pages[:max_pages]

    # Fallback: fetch each seed URL with httpx (no JS SPA expansion)
    logger.info("Apify unavailable or empty; falling back to httpx for %s urls", len(urls))
    fallback: list[CrawledPage] = []
    for url in urls[:max_pages]:
        page = crawl_url_httpx(url)
        if page:
            fallback.append(page)
    return fallback
