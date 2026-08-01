from django.conf import settings
from django.db import models

from apps.teams.models import BaseTeamModel


class AuditEvent(BaseTeamModel):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_events"
    )
    action = models.CharField(max_length=128, db_index=True)
    object_type = models.CharField(max_length=64, blank=True, default="")
    object_id = models.CharField(max_length=64, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["team", "created_at"]),
            models.Index(fields=["team", "action"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action}:{self.object_type}:{self.object_id}"
