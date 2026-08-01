from __future__ import annotations

from apps.audit.models import AuditEvent
from apps.teams.models import Team


def record_audit(
    *,
    team: Team,
    action: str,
    actor=None,
    object_type: str = "",
    object_id: str = "",
    metadata: dict | None = None,
    ip_address=None,
) -> AuditEvent:
    return AuditEvent.objects.create(
        team=team,
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=object_id,
        metadata=metadata or {},
        ip_address=ip_address,
    )
