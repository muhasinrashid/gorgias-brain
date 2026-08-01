from django.contrib import admin

from apps.agents.models import Agent


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ("name", "team", "status", "kill_switch", "shadow_mode")
    list_filter = ("status", "kill_switch", "shadow_mode")
    search_fields = ("name", "team__name", "team__slug")
