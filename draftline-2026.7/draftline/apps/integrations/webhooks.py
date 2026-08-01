"""Gorgias HTTP Integration webhook — ack fast, enqueue work.

Gorgias times out at 5s and retries 3x. We validate lightly, persist an event
row, enqueue sync, return 200 in well under 500ms.
"""

from __future__ import annotations

import hashlib
import json
import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.integrations.models import Connection, Provider
from apps.tickets.tasks import process_gorgias_webhook

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def gorgias_webhook(request, team_slug: str, connection_id: int):
    # Look up connection without decrypting credentials (webhook SA must not need KMS).
    try:
        connection = Connection.objects.select_related("team").get(
            pk=connection_id, team__slug=team_slug, provider=Provider.GORGIAS
        )
    except Connection.DoesNotExist:
        return JsonResponse({"ok": False, "error": "unknown connection"}, status=404)

    raw = request.body or b"{}"
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "invalid json"}, status=400)

    # Idempotency key from payload identity
    ticket_id = str(
        payload.get("ticket_id")
        or (payload.get("ticket") or {}).get("id")
        or payload.get("id")
        or ""
    )
    event_type = str(payload.get("type") or payload.get("event_type") or "unknown")
    digest = hashlib.sha256(raw).hexdigest()[:32]
    idempotency_key = f"{connection.id}:{event_type}:{ticket_id}:{digest}"

    process_gorgias_webhook.delay(
        connection.team_id,
        connection.id,
        ticket_id,
        event_type,
        idempotency_key,
        payload if isinstance(payload, dict) else {},
    )
    # Immediate ack for Gorgias HTTP widget / integration
    return HttpResponse(status=200)
