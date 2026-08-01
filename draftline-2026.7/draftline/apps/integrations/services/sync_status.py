"""Tenant-safe sync status for Integrations UI (no credentials / raw dumps)."""

from __future__ import annotations

from django.db.models import Count
from django.utils import timezone

from apps.integrations.models import Connection, ConnectionStatus, Provider
from apps.knowledge.models import Source, SourceType
from apps.tickets.models import BackfillCheckpoint, SyncPhase, Ticket


def friendly_error(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    lower = text.lower()
    if "429" in text or "too many requests" in lower:
        return "Gorgias asked us to slow down. We will keep importing and retry automatically."
    if "name resolution" in lower or "temporary failure" in lower or "connecterror" in lower:
        return "We could not reach Gorgias for a moment. Try again in a minute."
    if "timeout" in lower:
        return "The sync timed out. You can try again — progress is saved."
    if "run' object has no attribute" in lower or "timeout_secs" in lower:
        return "A crawl finished but we could not read the results. Try again."
    if len(text) > 180:
        return text[:177] + "…"
    return text


def _chip_for(*, connection: Connection, running: bool, failed: bool, ready: bool) -> str:
    if failed and not running:
        return "Needs attention"
    if ready and not running:
        return "Ready"
    return "Setting up"


def _gorgias_status(connection: Connection) -> dict:
    checkpoint = (
        BackfillCheckpoint.objects.filter(team=connection.team, connection=connection).first()
    )
    health = connection.health or {}
    ticket_count = Ticket.objects.filter(team=connection.team, connection=connection).count()
    source_counts = {
        row["source_type"]: row["n"]
        for row in Source.objects.filter(team=connection.team, connection=connection)
        .values("source_type")
        .annotate(n=Count("id"))
    }
    macros = source_counts.get(SourceType.MACRO, 0)
    articles = source_counts.get(SourceType.HELP_CENTER_ARTICLE, 0)

    phase = SyncPhase.QUEUED
    tickets_imported = ticket_count
    pages_scanned = 0
    checkpoint_status = ""
    started_at = None
    finished_at = None
    if checkpoint:
        phase = checkpoint.phase or SyncPhase.QUEUED
        tickets_imported = checkpoint.tickets_imported or ticket_count
        pages_scanned = checkpoint.pages_scanned or 0
        checkpoint_status = checkpoint.status or ""
        started_at = checkpoint.started_at
        finished_at = checkpoint.finished_at

    # Infer phase for older rows that predate the phase column.
    if checkpoint and not checkpoint.phase:
        if checkpoint_status == "COMPLETED" and health.get("sources_synced_at"):
            phase = SyncPhase.DONE
        elif checkpoint_status == "COMPLETED":
            phase = SyncPhase.SOURCES
        elif checkpoint_status == "RUNNING":
            phase = SyncPhase.TICKETS
        elif checkpoint_status == "FAILED":
            phase = SyncPhase.TICKETS

    running = checkpoint_status == "RUNNING" or (
        connection.status == ConnectionStatus.PENDING and phase != SyncPhase.DONE
    )
    # Sources phase may keep status RUNNING until knowledge sync finishes.
    if phase == SyncPhase.DONE and checkpoint_status == "COMPLETED":
        running = False
    if phase == SyncPhase.QUEUED and not checkpoint:
        running = connection.status in (ConnectionStatus.PENDING, ConnectionStatus.HEALTHY) and not ticket_count

    failed = (connection.status == ConnectionStatus.ERROR or checkpoint_status == "FAILED") and not running
    ready = phase == SyncPhase.DONE and connection.status == ConnectionStatus.HEALTHY and not running

    phase_label = {
        SyncPhase.QUEUED: "Queued — import will start shortly",
        SyncPhase.TICKETS: "Importing past tickets",
        SyncPhase.SOURCES: "Syncing macros and help articles",
        SyncPhase.DONE: "Up to date",
    }.get(phase, "Setting up")

    if failed and not running:
        phase_label = "Needs attention"

    progress_mode = "indeterminate" if running and phase == SyncPhase.TICKETS else "none"
    if phase == SyncPhase.SOURCES and running:
        progress_mode = "indeterminate"
    if phase == SyncPhase.DONE:
        progress_mode = "complete"

    detail = ""
    if phase == SyncPhase.TICKETS or (running and tickets_imported):
        detail = f"{tickets_imported:,} tickets imported so far"
        if pages_scanned:
            detail += f" · {pages_scanned} pages scanned"
    elif phase == SyncPhase.SOURCES:
        detail = f"{macros:,} macros · {articles:,} help articles"
    elif phase == SyncPhase.DONE:
        detail = f"{ticket_count:,} tickets · {macros:,} macros · {articles:,} help articles"

    return {
        "provider": connection.provider,
        "chip": _chip_for(connection=connection, running=running, failed=failed, ready=ready),
        "phase": phase,
        "phase_label": phase_label,
        "running": running,
        "ready": ready,
        "failed": failed and not running,
        "progress_mode": progress_mode,
        "progress_pct": 100 if progress_mode == "complete" else None,
        "detail": detail,
        "counts": {
            "tickets": ticket_count,
            "macros": macros,
            "articles": articles,
            "tickets_imported": tickets_imported,
            "pages_scanned": pages_scanned,
        },
        "last_sync_at": connection.last_sync_at.isoformat() if connection.last_sync_at else None,
        "started_at": started_at.isoformat() if started_at else None,
        "finished_at": finished_at.isoformat() if finished_at else None,
        "error_message": friendly_error(connection.last_error or (checkpoint.last_error if checkpoint else "")),
        "poll": running or (failed and connection.status == ConnectionStatus.PENDING),
    }


def _website_status(connection: Connection) -> dict:
    health = connection.health or {}
    config = connection.config or {}
    pages_target = int(config.get("max_pages") or health.get("pages_target") or 30)
    pages_done = int(
        health.get("pages_done")
        or health.get("web_pages_synced")
        or Source.objects.filter(
            team=connection.team, connection=connection, source_type=SourceType.WEB_PAGE
        ).count()
    )
    phase = health.get("phase") or ""
    if not phase:
        if connection.status == ConnectionStatus.HEALTHY and pages_done:
            phase = "DONE"
        elif connection.status == ConnectionStatus.ERROR:
            phase = "ERROR"
        else:
            phase = "CRAWLING"

    running = phase == "CRAWLING" or connection.status == ConnectionStatus.PENDING
    failed = connection.status == ConnectionStatus.ERROR or phase == "ERROR"
    ready = phase == "DONE" and connection.status == ConnectionStatus.HEALTHY

    if failed and not running:
        phase_label = "Needs attention"
    elif running:
        phase_label = "Crawling site"
    else:
        phase_label = "Up to date"

    pct = None
    progress_mode = "none"
    if running and pages_target > 0:
        progress_mode = "determinate"
        pct = min(100, int(round(100 * pages_done / pages_target))) if pages_done else 5
    elif ready:
        progress_mode = "complete"
        pct = 100

    detail = f"{pages_done:,} of {pages_target:,} pages"
    if ready:
        detail = f"{pages_done:,} pages stored"

    return {
        "provider": connection.provider,
        "chip": _chip_for(connection=connection, running=running, failed=failed, ready=ready),
        "phase": phase,
        "phase_label": phase_label,
        "running": running,
        "ready": ready,
        "failed": failed and not running,
        "progress_mode": progress_mode,
        "progress_pct": pct,
        "detail": detail,
        "counts": {
            "pages_done": pages_done,
            "pages_target": pages_target,
        },
        "last_sync_at": connection.last_sync_at.isoformat() if connection.last_sync_at else None,
        "started_at": health.get("started_at"),
        "finished_at": health.get("finished_at"),
        "error_message": friendly_error(connection.last_error or ""),
        "poll": running,
    }


def build_sync_status(connection: Connection) -> dict:
    if connection.provider == Provider.GORGIAS:
        return _gorgias_status(connection)
    if connection.provider == Provider.WEBSITE:
        return _website_status(connection)
    return {
        "provider": connection.provider,
        "chip": connection.get_status_display() if hasattr(connection, "get_status_display") else connection.status,
        "phase": "",
        "phase_label": connection.status,
        "running": False,
        "ready": connection.status == ConnectionStatus.HEALTHY,
        "failed": connection.status == ConnectionStatus.ERROR,
        "progress_mode": "none",
        "progress_pct": None,
        "detail": "",
        "counts": {},
        "last_sync_at": connection.last_sync_at.isoformat() if connection.last_sync_at else None,
        "started_at": None,
        "finished_at": None,
        "error_message": friendly_error(connection.last_error or ""),
        "poll": False,
    }


def mark_website_crawl_started(connection: Connection, *, pages_target: int) -> None:
    now = timezone.now().isoformat()
    connection.status = ConnectionStatus.PENDING
    connection.health = {
        **(connection.health or {}),
        "phase": "CRAWLING",
        "pages_done": 0,
        "pages_target": pages_target,
        "started_at": now,
        "finished_at": None,
    }
    connection.save(update_fields=["status", "health", "updated_at"])


def mark_website_crawl_progress(connection: Connection, *, pages_done: int, pages_target: int) -> None:
    connection.health = {
        **(connection.health or {}),
        "phase": "CRAWLING",
        "pages_done": pages_done,
        "pages_target": pages_target,
    }
    connection.save(update_fields=["health", "updated_at"])
