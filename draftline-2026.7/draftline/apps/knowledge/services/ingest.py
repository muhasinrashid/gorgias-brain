"""Ingest Gorgias macros and Help Center articles into knowledge.Source."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime

from django.utils import timezone

from apps.integrations.models import Connection, ConnectionStatus
from apps.integrations.providers.gorgias.adapter import adapter_from_connection
from apps.knowledge.models import Source, SourceType
from apps.teams.celery import team_task
from apps.utils.locks import single_flight

logger = logging.getLogger(__name__)

CRAWL_LOCK_TIMEOUT = 2 * 60 * 60

_MACRO_VAR = re.compile(r"\{\{[^}]+\}\}")


def _checksum(text: str) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()


def _macro_body(raw: dict) -> str:
    # Gorgias macros store actions; extract reply body when present.
    parts: list[str] = []
    for action in raw.get("actions") or []:
        if not isinstance(action, dict):
            continue
        name = (action.get("name") or action.get("type") or "").lower()
        args = action.get("arguments") or action.get("args") or {}
        if "body" in args:
            parts.append(str(args.get("body") or ""))
        elif "body_html" in args:
            parts.append(str(args.get("body_html") or ""))
        elif "body_text" in args:
            parts.append(str(args.get("body_text") or ""))
        elif "reply" in name or "message" in name:
            parts.append(str(args))
    if parts:
        return "\n\n".join(p for p in parts if p)
    return str(raw.get("body") or raw.get("text") or "")


def _macro_variables(text: str) -> list[str]:
    return sorted(set(_MACRO_VAR.findall(text or "")))


def upsert_macro_source(*, team, connection: Connection, raw: dict) -> Source:
    external_id = str(raw.get("id") or "")
    title = raw.get("name") or raw.get("title") or f"Macro {external_id}"
    body = _macro_body(raw)
    usage = int(raw.get("usage") or raw.get("usage_count") or 0)
    source, _ = Source.objects.update_or_create(
        team=team,
        source_type=SourceType.MACRO,
        external_id=external_id,
        defaults={
            "connection": connection,
            "title": title[:512],
            "raw_content": body,
            "normalised_content": body,  # keep variables; do not treat as prose facts
            "language": (raw.get("language") or "")[:16],
            "checksum": _checksum(body),
            "synced_at": timezone.now(),
            "is_active": not bool(raw.get("archived") or raw.get("deleted")),
            "usage_count": usage,
            "metadata": {
                "variables": _macro_variables(body),
                "tags": raw.get("tags") or [],
                "usage": usage,
                "as_phrasing_only": True,
            },
        },
    )
    return source


def upsert_article_source(*, team, connection: Connection, raw: dict) -> Source:
    external_id = str(raw.get("id") or raw.get("slug") or "")
    title = raw.get("title") or raw.get("name") or f"Article {external_id}"
    body = raw.get("body_text") or raw.get("content") or raw.get("body_html") or raw.get("body") or ""
    if isinstance(body, dict):
        body = str(body)
    url = raw.get("url") or raw.get("public_url") or ""
    source, _ = Source.objects.update_or_create(
        team=team,
        source_type=SourceType.HELP_CENTER_ARTICLE,
        external_id=external_id,
        defaults={
            "connection": connection,
            "title": str(title)[:512],
            "url": str(url)[:200] if url else "",
            "raw_content": str(body),
            "normalised_content": str(body),
            "language": str(raw.get("locale") or raw.get("language") or "")[:16],
            "checksum": _checksum(str(body)),
            "synced_at": timezone.now(),
            "is_active": not bool(raw.get("deleted") or raw.get("archived")),
            "metadata": {"category": raw.get("category") or raw.get("category_id")},
        },
    )
    return source


@team_task(bind=True, name="knowledge.ingest_gorgias_sources", queue="sync", max_retries=2)
def ingest_gorgias_sources(self, team_id: int, connection_id: int):
    with single_flight(f"ingest_gorgias_sources:{connection_id}", timeout=CRAWL_LOCK_TIMEOUT) as acquired:
        if not acquired:
            logger.info("source sync already running for connection %s; skipping", connection_id)
            return {"skipped": True, "reason": "already running"}
        return _run_gorgias_source_ingest(team_id=team_id, connection_id=connection_id)


def _run_gorgias_source_ingest(*, team_id: int, connection_id: int):
    from apps.teams.models import Team
    from apps.tickets.models import BackfillCheckpoint, SyncPhase

    team = Team.objects.get(pk=team_id)
    connection = Connection.objects.get(pk=connection_id, team=team)
    checkpoint = BackfillCheckpoint.objects.filter(team=team, connection=connection).first()
    if checkpoint:
        checkpoint.phase = SyncPhase.SOURCES
        checkpoint.status = "RUNNING"
        checkpoint.save(update_fields=["phase", "status", "updated_at"])

    adapter = adapter_from_connection(connection)
    macros = 0
    articles = 0
    try:
        for raw in adapter.iter_macros():
            upsert_macro_source(team=team, connection=connection, raw=raw)
            macros += 1
        for raw in adapter.iter_help_center_articles():
            upsert_article_source(team=team, connection=connection, raw=raw)
            articles += 1
        now = timezone.now()
        connection.health = {
            **(connection.health or {}),
            "macros_synced": macros,
            "articles_synced": articles,
            "sources_synced_at": now.isoformat(),
        }
        connection.status = ConnectionStatus.HEALTHY
        connection.last_sync_at = now
        connection.last_error = ""
        connection.save(update_fields=["health", "status", "last_sync_at", "last_error", "updated_at"])
        if checkpoint:
            checkpoint.phase = SyncPhase.DONE
            checkpoint.status = "COMPLETED"
            checkpoint.last_error = ""
            checkpoint.finished_at = now
            checkpoint.save(update_fields=["phase", "status", "last_error", "finished_at", "updated_at"])
        return {"macros": macros, "articles": articles}
    except Exception as exc:
        connection.status = ConnectionStatus.ERROR
        connection.last_error = str(exc)
        connection.save(update_fields=["status", "last_error", "updated_at"])
        if checkpoint:
            checkpoint.status = "FAILED"
            checkpoint.last_error = str(exc)
            checkpoint.save(update_fields=["status", "last_error", "updated_at"])
        raise
    finally:
        adapter.close()


def _external_id_for_url(url: str) -> str:
    normalized = (url or "").strip()
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:40]
    return f"web:{digest}"


def upsert_web_page_source(*, team, connection: Connection, url: str, title: str, content: str, metadata: dict | None = None):
    external_id = _external_id_for_url(url)
    source, _ = Source.objects.update_or_create(
        team=team,
        source_type=SourceType.WEB_PAGE,
        external_id=external_id,
        defaults={
            "connection": connection,
            "title": (title or url)[:512],
            "url": url[:200],
            "raw_content": content,
            "normalised_content": content,
            "checksum": _checksum(content),
            "synced_at": timezone.now(),
            "is_active": True,
            "metadata": metadata or {},
        },
    )
    return source


@team_task(bind=True, name="knowledge.ingest_website", queue="sync", max_retries=2)
def ingest_website(self, team_id: int, connection_id: int):
    with single_flight(f"ingest_website:{connection_id}", timeout=CRAWL_LOCK_TIMEOUT) as acquired:
        if not acquired:
            logger.info("website crawl already running for connection %s; skipping", connection_id)
            return {"skipped": True, "reason": "already running"}
        return _run_website_ingest(team_id=team_id, connection_id=connection_id)


def _run_website_ingest(*, team_id: int, connection_id: int):
    from django.utils import timezone as dj_tz

    from apps.integrations.services.sync_status import mark_website_crawl_progress, mark_website_crawl_started
    from apps.knowledge.services.web_crawl import crawl_urls
    from apps.teams.models import Team

    team = Team.objects.get(pk=team_id)
    connection = Connection.objects.get(pk=connection_id, team=team)
    config = connection.config or {}
    seed_urls = list(config.get("seed_urls") or [])
    max_pages = int(config.get("max_pages") or 30)
    max_depth = int(config.get("max_depth") or 2)

    mark_website_crawl_started(connection, pages_target=max_pages)
    connection.last_error = ""
    connection.save(update_fields=["last_error", "updated_at"])

    try:
        pages = crawl_urls(seed_urls, max_pages=max_pages, max_depth=max_depth)
        count = 0
        crawler_used = ""
        for page in pages:
            upsert_web_page_source(
                team=team,
                connection=connection,
                url=page.url,
                title=page.title,
                content=page.content,
                metadata={"crawler": page.crawler, **(page.metadata or {})},
            )
            count += 1
            crawler_used = page.crawler or crawler_used
            if count == 1 or count % 5 == 0:
                mark_website_crawl_progress(connection, pages_done=count, pages_target=max_pages)
        now = dj_tz.now()
        connection.status = ConnectionStatus.HEALTHY
        connection.last_sync_at = now
        connection.last_error = ""
        connection.health = {
            **(connection.health or {}),
            "phase": "DONE",
            "pages_done": count,
            "pages_target": max_pages,
            "web_pages_synced": count,
            "crawler": crawler_used or "none",
            "sources_synced_at": now.isoformat(),
            "finished_at": now.isoformat(),
            "seed_url_count": len(seed_urls),
        }
        connection.save(update_fields=["status", "last_sync_at", "last_error", "health", "updated_at"])
        return {"pages": count, "crawler": crawler_used}
    except Exception as exc:
        connection.status = ConnectionStatus.ERROR
        connection.last_error = str(exc)
        connection.health = {
            **(connection.health or {}),
            "phase": "ERROR",
            "finished_at": dj_tz.now().isoformat(),
        }
        connection.save(update_fields=["status", "last_error", "health", "updated_at"])
        raise
