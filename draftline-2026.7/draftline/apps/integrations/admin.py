from django.contrib import admin

from apps.integrations.models import AgentConnection, Connection


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = ("display_name", "team", "provider", "status", "last_sync_at")
    list_filter = ("provider", "status")
    search_fields = ("display_name", "team__name", "team__slug")
    # credentials_encrypted intentionally omitted from fieldsets
    exclude = ("credentials_encrypted",)
    readonly_fields = ("created_at", "updated_at", "capabilities", "health")


@admin.register(AgentConnection)
class AgentConnectionAdmin(admin.ModelAdmin):
    list_display = ("agent", "connection", "team")
    list_filter = ("connection__provider",)
