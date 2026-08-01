from django.contrib import admin

from apps.knowledge.models import Chunk, CuratedKnowledge, PlatformCrawlerSettings, ResolutionPair, Source


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("title", "source_type", "team", "is_active", "usage_count", "synced_at")
    list_filter = ("source_type", "is_active")
    search_fields = ("title", "external_id", "url")


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ("source", "ordinal", "team", "token_count", "embedder_version")
    list_filter = ("embedder_version",)
    search_fields = ("text", "source__title")


@admin.register(ResolutionPair)
class ResolutionPairAdmin(admin.ModelAdmin):
    list_display = ("id", "team", "intent", "language", "is_exemplar", "quality_score")
    list_filter = ("is_exemplar", "language")
    search_fields = ("question_text", "resolution_text")


@admin.register(CuratedKnowledge)
class CuratedKnowledgeAdmin(admin.ModelAdmin):
    list_display = ("id", "team", "status", "intent", "is_deidentified", "approved_at")
    list_filter = ("status", "is_deidentified")
    search_fields = ("question", "answer")


@admin.register(PlatformCrawlerSettings)
class PlatformCrawlerSettingsAdmin(admin.ModelAdmin):
    list_display = ("id", "enabled", "apify_actor", "default_max_pages", "hard_max_pages", "updated_at")
    fields = (
        "enabled",
        "apify_actor",
        "default_max_depth",
        "default_max_pages",
        "hard_max_pages",
        "last_health_check_at",
        "last_error",
    )
    readonly_fields = ("last_health_check_at", "last_error")

    def has_add_permission(self, request):
        return not PlatformCrawlerSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
