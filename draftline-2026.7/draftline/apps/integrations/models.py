from django.db import models

from apps.teams.models import BaseTeamModel


class Provider(models.TextChoices):
    GORGIAS = "GORGIAS", "Gorgias"
    BIGCOMMERCE = "BIGCOMMERCE", "BigCommerce"
    GLOBAL_E = "GLOBAL_E", "Global-E"
    WEBSITE = "WEBSITE", "Website"
    FILES = "FILES", "Files"


class ConnectionStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    HEALTHY = "HEALTHY", "Healthy"
    DEGRADED = "DEGRADED", "Degraded"
    ERROR = "ERROR", "Error"
    DISCONNECTED = "DISCONNECTED", "Disconnected"


class Connection(BaseTeamModel):
    provider = models.CharField(max_length=32, choices=Provider.choices)
    # Encrypted blob — never expose via serializers/API/admin readonly carefully
    credentials_encrypted = models.BinaryField(blank=True, default=b"")
    config = models.JSONField(default=dict, blank=True)
    capabilities = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=32, choices=ConnectionStatus.choices, default=ConnectionStatus.PENDING)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    health = models.JSONField(default=dict, blank=True)
    display_name = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        unique_together = ("team", "provider", "display_name")
        indexes = [
            models.Index(fields=["team", "provider"]),
        ]

    def __str__(self) -> str:
        return self.display_name or f"{self.provider}:{self.pk}"

    def set_credentials(self, credentials: dict) -> None:
        from apps.integrations.vault import get_encryptor

        self.credentials_encrypted = get_encryptor().encrypt(credentials)

    def get_credentials(self) -> dict:
        from apps.integrations.vault import get_encryptor

        if not self.credentials_encrypted:
            return {}
        return get_encryptor().decrypt(bytes(self.credentials_encrypted))

    def to_public_dict(self) -> dict:
        """Safe representation — credentials must never appear."""
        return {
            "id": self.pk,
            "team_id": self.team_id,
            "provider": self.provider,
            "config": self.config,
            "capabilities": self.capabilities,
            "status": self.status,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_error": self.last_error,
            "health": self.health,
            "display_name": self.display_name,
        }


class AgentConnection(BaseTeamModel):
    agent = models.ForeignKey("agents.Agent", on_delete=models.CASCADE, related_name="agent_connections")
    connection = models.ForeignKey(Connection, on_delete=models.CASCADE, related_name="agent_links")

    class Meta:
        unique_together = ("agent", "connection")
