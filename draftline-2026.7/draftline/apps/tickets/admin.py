from django.contrib import admin

from apps.tickets.models import BackfillCheckpoint, QualificationGoldLabel, Ticket, TicketMessage


class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    extra = 0
    fields = ("sequence", "direction", "author_type", "external_id", "is_resolving_reply")
    readonly_fields = fields


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("external_id", "subject", "team", "status", "qualification", "customer_email")
    list_filter = ("qualification", "status")
    search_fields = ("external_id", "subject", "customer_email")
    inlines = [TicketMessageInline]


@admin.register(BackfillCheckpoint)
class BackfillCheckpointAdmin(admin.ModelAdmin):
    list_display = ("connection", "team", "status", "tickets_imported", "cursor")


@admin.register(QualificationGoldLabel)
class QualificationGoldLabelAdmin(admin.ModelAdmin):
    list_display = ("ticket", "label", "team", "labeled_by", "created_at")
    list_filter = ("label",)
    search_fields = ("ticket__external_id", "ticket__subject", "notes")
