from django.conf import settings
from django.db import models
from pgvector.django import VectorField

from apps.teams.models import BaseTeamModel
from apps.utils.models import BaseModel


class SourceType(models.TextChoices):
    HELP_CENTER_ARTICLE = "HELP_CENTER_ARTICLE", "Help Center article"
    MACRO = "MACRO", "Macro"
    TICKET = "TICKET", "Ticket"
    WEB_PAGE = "WEB_PAGE", "Web page"
    FILE = "FILE", "File"
    CURATED_QA = "CURATED_QA", "Curated Q&A"


class PlatformCrawlerSettings(BaseModel):
    """Singleton: Draftline-owned Apify config. Tenants never see this."""

    apify_api_key_encrypted = models.BinaryField(blank=True, default=b"")
    apify_actor = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Apify actor id, e.g. org~draftline-web-crawler (leave blank until custom actor ships).",
    )
    enabled = models.BooleanField(default=True)
    default_max_depth = models.PositiveIntegerField(default=2)
    default_max_pages = models.PositiveIntegerField(default=30)
    hard_max_pages = models.PositiveIntegerField(default=100)
    last_health_check_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Platform crawler settings"
        verbose_name_plural = "Platform crawler settings"

    def __str__(self) -> str:
        return "Platform crawler settings"

    @classmethod
    def get_solo(cls) -> "PlatformCrawlerSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def set_apify_api_key(self, api_key: str) -> None:
        from apps.integrations.vault import get_encryptor

        if not api_key:
            self.apify_api_key_encrypted = b""
            return
        self.apify_api_key_encrypted = get_encryptor().encrypt({"api_key": api_key})

    def get_apify_api_key(self) -> str:
        from django.conf import settings

        from apps.integrations.vault import get_encryptor

        if self.apify_api_key_encrypted:
            data = get_encryptor().decrypt(bytes(self.apify_api_key_encrypted))
            return str(data.get("api_key") or "")
        return getattr(settings, "APIFY_API_KEY", "") or ""

    def masked_api_key(self) -> str:
        key = self.get_apify_api_key()
        if not key:
            return ""
        if len(key) <= 8:
            return "••••"
        return f"{key[:4]}…{key[-4:]}"

    def resolve_actor(self) -> str:
        from django.conf import settings

        return (self.apify_actor or getattr(settings, "APIFY_ACTOR", "") or "").strip()


class Source(BaseTeamModel):
    connection = models.ForeignKey(
        "integrations.Connection",
        on_delete=models.CASCADE,
        related_name="sources",
        null=True,
        blank=True,
    )
    source_type = models.CharField(max_length=32, choices=SourceType.choices)
    external_id = models.CharField(max_length=128, blank=True, default="")
    title = models.CharField(max_length=512, blank=True, default="")
    url = models.URLField(blank=True, default="")
    raw_content = models.TextField(blank=True, default="")
    normalised_content = models.TextField(blank=True, default="")
    language = models.CharField(max_length=16, blank=True, default="")
    checksum = models.CharField(max_length=64, blank=True, default="")
    synced_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    usage_count = models.PositiveIntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("team", "source_type", "external_id")
        indexes = [
            models.Index(fields=["team", "source_type"]),
            models.Index(fields=["team", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.source_type}:{self.title or self.external_id}"


EMBEDDING_DIMENSIONS = 1536  # text-embedding-3-small


class Chunk(BaseTeamModel):
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="chunks")
    ordinal = models.PositiveIntegerField(default=0)
    text = models.TextField()
    token_count = models.PositiveIntegerField(default=0)
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True, blank=True)
    char_offset_start = models.PositiveIntegerField(default=0)
    char_offset_end = models.PositiveIntegerField(default=0)
    language = models.CharField(max_length=16, blank=True, default="")
    embedder_version = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        unique_together = ("team", "source", "ordinal")
        indexes = [
            models.Index(fields=["team", "source"]),
        ]
        ordering = ["source_id", "ordinal"]

    def __str__(self) -> str:
        return f"chunk:{self.source_id}:{self.ordinal}"


class ResolutionPair(BaseTeamModel):
    source = models.ForeignKey(
        Source, on_delete=models.SET_NULL, null=True, blank=True, related_name="resolution_pairs"
    )
    source_ticket_ids = models.JSONField(default=list, blank=True)
    question_text = models.TextField()
    context_summary = models.TextField(blank=True, default="")
    resolution_text = models.TextField()
    intent = models.CharField(max_length=128, blank=True, default="")
    language = models.CharField(max_length=16, blank=True, default="")
    quality_score = models.FloatField(null=True, blank=True)
    is_exemplar = models.BooleanField(default=False)
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True, blank=True)
    embedder_version = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["team", "intent"]),
            models.Index(fields=["team", "is_exemplar"]),
        ]

    def __str__(self) -> str:
        return f"rp:{self.pk}:{(self.question_text or '')[:40]}"


class CuratedStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    APPROVED = "APPROVED", "Approved"
    RETIRED = "RETIRED", "Retired"


class CuratedKnowledge(BaseTeamModel):
    question = models.TextField()
    answer = models.TextField()
    intent = models.CharField(max_length=128, blank=True, default="")
    language = models.CharField(max_length=16, blank=True, default="")
    status = models.CharField(max_length=16, choices=CuratedStatus.choices, default=CuratedStatus.DRAFT)
    created_from_delta = models.CharField(max_length=64, blank=True, default="")  # FK later when Delta exists
    source_ticket_ids = models.JSONField(default=list, blank=True)
    is_deidentified = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_curated_knowledge",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True, blank=True)
    embedder_version = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["team", "status"]),
            models.Index(fields=["team", "intent"]),
        ]

    def __str__(self) -> str:
        return f"curated:{self.status}:{(self.question or '')[:40]}"
