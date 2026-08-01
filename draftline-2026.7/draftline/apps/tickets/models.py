from django.conf import settings
from django.db import models

from apps.teams.models import BaseTeamModel


class Qualification(models.TextChoices):
    SUPPORT = "SUPPORT", "Support"
    SPAM_PHISHING = "SPAM_PHISHING", "Spam / phishing"
    MARKETING_INBOUND = "MARKETING_INBOUND", "Marketing inbound"
    SYSTEM_NOTIFICATION = "SYSTEM_NOTIFICATION", "System notification"
    SOCIAL_NOTIFICATION = "SOCIAL_NOTIFICATION", "Social notification"
    VENDOR_PITCH = "VENDOR_PITCH", "Vendor pitch"
    INTERNAL = "INTERNAL", "Internal"
    UNCLEAR = "UNCLEAR", "Unclear"


class MessageDirection(models.TextChoices):
    INBOUND = "INBOUND", "Inbound"
    OUTBOUND = "OUTBOUND", "Outbound"
    INTERNAL_NOTE = "INTERNAL_NOTE", "Internal note"


class AuthorType(models.TextChoices):
    CUSTOMER = "CUSTOMER", "Customer"
    AGENT = "AGENT", "Agent"
    SYSTEM = "SYSTEM", "System"
    BOT = "BOT", "Bot"


class Ticket(BaseTeamModel):
    connection = models.ForeignKey(
        "integrations.Connection", on_delete=models.CASCADE, related_name="tickets"
    )
    external_id = models.CharField(max_length=64, db_index=True)
    subject = models.CharField(max_length=512, blank=True, default="")
    channel = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=64, blank=True, default="")
    created_at_external = models.DateTimeField(null=True, blank=True)
    closed_at_external = models.DateTimeField(null=True, blank=True)
    customer_email = models.EmailField(blank=True, default="")
    customer_external_id = models.CharField(max_length=64, blank=True, default="")
    qualification = models.CharField(
        max_length=32, choices=Qualification.choices, default=Qualification.UNCLEAR
    )
    qualification_confidence = models.FloatField(null=True, blank=True)
    qualifier_version = models.CharField(max_length=64, blank=True, default="")
    intent = models.CharField(max_length=128, blank=True, default="")
    language = models.CharField(max_length=16, blank=True, default="")
    sentiment = models.CharField(max_length=32, blank=True, default="")
    csat_score = models.FloatField(null=True, blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("team", "external_id")
        indexes = [
            models.Index(fields=["team", "external_id"]),
            models.Index(fields=["team", "created_at"]),
            models.Index(fields=["team", "qualification"]),
        ]

    def __str__(self) -> str:
        return f"{self.external_id}: {self.subject[:40]}"


class TicketMessage(BaseTeamModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    external_id = models.CharField(max_length=64, db_index=True)
    sequence = models.PositiveIntegerField(default=0)
    direction = models.CharField(max_length=32, choices=MessageDirection.choices)
    author_type = models.CharField(max_length=32, choices=AuthorType.choices)
    author_external_id = models.CharField(max_length=64, blank=True, default="")
    author_name = models.CharField(max_length=255, blank=True, default="")
    raw_body_html = models.TextField(blank=True, default="")
    raw_body_text = models.TextField(blank=True, default="")
    normalised_text = models.TextField(blank=True, default="")
    is_autoresponder = models.BooleanField(default=False)
    is_resolving_reply = models.BooleanField(default=False)
    classifier_version = models.CharField(max_length=64, blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("team", "external_id")
        ordering = ["sequence", "sent_at", "id"]
        indexes = [
            models.Index(fields=["team", "ticket"]),
        ]

    def __str__(self) -> str:
        return f"{self.ticket_id}:{self.external_id}"


class SyncPhase(models.TextChoices):
    QUEUED = "QUEUED", "Queued"
    TICKETS = "TICKETS", "Importing tickets"
    SOURCES = "SOURCES", "Syncing knowledge sources"
    DONE = "DONE", "Done"


class BackfillCheckpoint(BaseTeamModel):
    connection = models.ForeignKey(
        "integrations.Connection", on_delete=models.CASCADE, related_name="backfill_checkpoints"
    )
    cursor = models.CharField(max_length=512, blank=True, default="")
    tickets_imported = models.PositiveIntegerField(default=0)
    pages_scanned = models.PositiveIntegerField(default=0)
    phase = models.CharField(max_length=16, choices=SyncPhase.choices, default=SyncPhase.QUEUED)
    status = models.CharField(max_length=32, default="RUNNING")
    last_error = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("team", "connection")


class QualificationGoldLabel(BaseTeamModel):
    """Human gold label for qualification eval (M1 precision gate)."""

    ticket = models.OneToOneField(Ticket, on_delete=models.CASCADE, related_name="gold_label")
    label = models.CharField(max_length=32, choices=Qualification.choices)
    labeled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="qualification_labels"
    )
    notes = models.TextField(blank=True, default="")

    def __str__(self) -> str:
        return f"{self.ticket_id}:{self.label}"
