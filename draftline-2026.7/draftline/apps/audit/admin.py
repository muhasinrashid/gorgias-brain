from django.contrib import admin

from apps.audit.models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("action", "team", "actor", "object_type", "object_id", "created_at")
    list_filter = ("action",)
    search_fields = ("action", "object_id", "team__slug")
    readonly_fields = ("created_at", "updated_at", "metadata")
