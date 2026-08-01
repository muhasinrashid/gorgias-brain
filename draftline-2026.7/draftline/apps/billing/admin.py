from django.contrib import admin

from apps.billing.models import TeamEntitlement


@admin.register(TeamEntitlement)
class TeamEntitlementAdmin(admin.ModelAdmin):
    list_display = ("team", "plan_code", "status", "interactions_used", "interactions_included", "billing_provider")
    list_filter = ("plan_code", "status", "billing_provider")
    search_fields = ("team__name", "team__slug", "provider_ref", "notes")
    readonly_fields = ("created_at", "updated_at")
