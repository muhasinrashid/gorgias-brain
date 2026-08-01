from __future__ import annotations

import logging
import time

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.integrations.models import Connection, ConnectionStatus
from apps.integrations.providers.gorgias.adapter import adapter_from_connection
from apps.teams.celery import team_task
from apps.tickets.models import BackfillCheckpoint, Ticket, TicketMessage
from apps.tickets.services.normalisation import classify_author, normalise_message_body
from apps.tickets.services.qualification import apply_qualification_to_ticket, is_autoresponder_text
from apps.tickets.services.resolving import annotate_thread_messages
from apps.utils.locks import lock_cache, single_flight

logger = logging.getLogger(__name__)

BACKFILL_LOCK_TIMEOUT = 6 * 60 * 60


def _fit(value, max_length: int) -> str:
    """Provider strings have no length contract; the column does."""
    return (value or "")[:max_length]


def upsert_ticket_from_payload(*, team, connection: Connection, payload) -> Ticket:
    ticket, _ = Ticket.objects.update_or_create(
        team=team,
        external_id=_fit(payload.external_id, 64),
        defaults={
            "connection": connection,
            "subject": _fit(payload.subject, 512),
            "channel": _fit(payload.channel, 64),
            "status": _fit(payload.status, 64),
            "created_at_external": payload.created_at,
            "closed_at_external": payload.closed_at,
            "customer_email": _fit(payload.customer_email, 254),
            "customer_external_id": _fit(payload.customer_external_id, 64),
            "raw": payload.raw,
        },
    )
    return ticket


def upsert_messages(*, team, ticket: Ticket, raw_messages: list[dict]) -> int:
    count = 0
    for idx, raw in enumerate(raw_messages):
        external_id = str(raw.get("id") or f"{ticket.external_id}-{idx}")
        author_type, direction = classify_author(raw)
        body_html = raw.get("body_html") or ""
        body_text = raw.get("body_text") or raw.get("stripped_text") or ""
        normalised = normalise_message_body(body_html=body_html, body_text=body_text)
        sender = raw.get("sender") or {}
        autoresponder = author_type == "AGENT" and is_autoresponder_text(normalised or body_text)
        TicketMessage.objects.update_or_create(
            team=team,
            external_id=_fit(external_id, 64),
            defaults={
                "ticket": ticket,
                "sequence": idx,
                "direction": direction,
                "author_type": author_type,
                "author_external_id": _fit(str(sender.get("id") or ""), 64),
                "author_name": _fit(sender.get("name") or sender.get("email") or "", 255),
                "raw_body_html": body_html,
                "raw_body_text": body_text,
                "normalised_text": normalised,
                "is_autoresponder": autoresponder,
                "classifier_version": "rules-v1" if autoresponder else "",
                "sent_at": ticket.created_at_external if not raw.get("created_datetime") else None,
                "raw": raw,
            },
        )
        count += 1
    return count


@team_task(
    bind=True,
    name="tickets.backfill_gorgias",
    queue="backfill",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def backfill_gorgias_tickets(self, team_id: int, connection_id: int, max_pages: int = 50):
    """Idempotent closed-ticket backfill. Checkpointed by cursor."""
    with single_flight(f"backfill_gorgias:{connection_id}", timeout=BACKFILL_LOCK_TIMEOUT) as acquired:
        if not acquired:
            logger.info("backfill already running for connection %s; skipping", connection_id)
            return {"skipped": True, "reason": "already running"}
        return _run_backfill(team_id=team_id, connection_id=connection_id, max_pages=max_pages)


def _run_backfill(*, team_id: int, connection_id: int, max_pages: int):
    from apps.teams.models import Team
    from apps.tickets.models import SyncPhase

    team = Team.objects.get(pk=team_id)
    connection = Connection.objects.get(pk=connection_id, team=team)
    checkpoint, _ = BackfillCheckpoint.objects.get_or_create(team=team, connection=connection)
    now = timezone.now()
    checkpoint.status = "RUNNING"
    checkpoint.phase = SyncPhase.TICKETS
    checkpoint.last_error = ""
    if not checkpoint.started_at:
        checkpoint.started_at = now
    checkpoint.finished_at = None
    checkpoint.save(update_fields=["status", "phase", "last_error", "started_at", "finished_at", "updated_at"])
    connection.status = ConnectionStatus.PENDING
    connection.last_error = ""
    connection.save(update_fields=["status", "last_error", "updated_at"])

    adapter = adapter_from_connection(connection)
    try:
        pages = 0
        cursor = checkpoint.cursor or None
        while pages < max_pages:
            page = adapter.list_closed_tickets_page(cursor=cursor)
            for payload in page.tickets:
                with transaction.atomic():
                    ticket = upsert_ticket_from_payload(team=team, connection=connection, payload=payload)
                    try:
                        messages = adapter.fetch_messages(payload.external_id)
                        upsert_messages(team=team, ticket=ticket, raw_messages=messages)
                    except Exception:
                        logger.exception("message fetch failed for %s", payload.external_id)
                    apply_qualification_to_ticket(
                        ticket, backend=getattr(settings, "QUALIFIER_BACKEND", "rules")
                    )
                    annotate_thread_messages(ticket)
                checkpoint.tickets_imported += 1
                time.sleep(0.3)  # gentle with Gorgias — see EXTERNAL_API_NOTES
            pages += 1
            cursor = page.next_cursor
            checkpoint.cursor = cursor or ""
            checkpoint.pages_scanned = (checkpoint.pages_scanned or 0) + 1
            checkpoint.save(update_fields=["cursor", "tickets_imported", "pages_scanned", "updated_at"])
            if not cursor:
                break

        # Ticket pass done — chain macros / Help Center without exposing a second button.
        from apps.knowledge.services.ingest import ingest_gorgias_sources

        checkpoint.phase = SyncPhase.SOURCES
        checkpoint.last_error = ""
        checkpoint.save(update_fields=["phase", "last_error", "updated_at"])
        connection.last_error = ""
        connection.save(update_fields=["last_error", "updated_at"])
        ingest_gorgias_sources.delay(team_id, connection_id)
        return {"imported": checkpoint.tickets_imported, "phase": SyncPhase.SOURCES}
    except Exception as exc:
        checkpoint.status = "FAILED"
        checkpoint.last_error = str(exc)
        checkpoint.save(update_fields=["status", "last_error", "updated_at"])
        connection.status = ConnectionStatus.ERROR
        connection.last_error = str(exc)
        connection.save(update_fields=["status", "last_error", "updated_at"])
        raise
    finally:
        adapter.close()


@team_task(
    bind=True,
    name="tickets.process_gorgias_webhook",
    queue="sync",
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def process_gorgias_webhook(
    self,
    team_id: int,
    connection_id: int,
    ticket_external_id: str,
    event_type: str,
    idempotency_key: str,
    payload: dict,
):
    """Fetch/upsert a single ticket after a Gorgias HTTP Integration event."""
    from apps.teams.models import Team

    # Simple idempotency via Redis key for M1; replace with WebhookEvent model in hardening.
    cache = lock_cache()
    cache_key = f"gorgias_webhook:{idempotency_key}"
    if not cache.add(cache_key, 1, 60 * 60 * 24):
        return {"skipped": True, "reason": "duplicate"}

    team = Team.objects.get(pk=team_id)
    connection = Connection.objects.get(pk=connection_id, team=team)
    if not ticket_external_id:
        ticket_external_id = str((payload.get("ticket") or {}).get("id") or payload.get("id") or "")
    if not ticket_external_id:
        return {"skipped": True, "reason": "no ticket id"}

    adapter = adapter_from_connection(connection)
    try:
        fetched = adapter.fetch_ticket(ticket_external_id)
        if not fetched:
            return {"ok": False, "reason": "ticket not found"}
        with transaction.atomic():
            ticket = upsert_ticket_from_payload(team=team, connection=connection, payload=fetched)
            messages = adapter.fetch_messages(ticket_external_id)
            upsert_messages(team=team, ticket=ticket, raw_messages=messages)
            apply_qualification_to_ticket(ticket, backend=getattr(settings, "QUALIFIER_BACKEND", "rules"))
            annotate_thread_messages(ticket)
        return {"ok": True, "ticket_id": ticket.id, "event_type": event_type}
    finally:
        adapter.close()
