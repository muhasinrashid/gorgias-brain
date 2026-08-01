from django.conf import settings
from django.db import models

from apps.teams.models import BaseTeamModel


class AgentStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    PAUSED = "PAUSED", "Paused"
    ARCHIVED = "ARCHIVED", "Archived"


class Agent(BaseTeamModel):
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=32, choices=AgentStatus.choices, default=AgentStatus.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_agents"
    )
    kill_switch = models.BooleanField(
        default=False,
        help_text="When True, generation stops immediately for this agent.",
    )
    shadow_mode = models.BooleanField(
        default=True,
        help_text="Generate and score drafts but do not deliver. Default on per spec.",
    )
    settings = models.JSONField(default=dict, blank=True)
    # Pointer for InstructionVersion (M4) — nullable until instructions land
    current_instructions = models.TextField(blank=True, default="")

    class Meta:
        indexes = [models.Index(fields=["team", "status"])]

    def __str__(self) -> str:
        return self.name

    def may_generate(self) -> bool:
        return self.status == AgentStatus.ACTIVE and not self.kill_switch
