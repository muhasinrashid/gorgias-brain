"""Corpus Report — M1 milestone artefact."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncWeek
from django.utils import timezone

from apps.knowledge.models import Source, SourceType
from apps.tickets.models import Ticket, TicketMessage


def build_corpus_report(team) -> dict:
    tickets = Ticket.objects.filter(team=team)
    messages = TicketMessage.objects.filter(team=team)
    now = timezone.now()

    qualification = list(tickets.values("qualification").annotate(c=Count("id")).order_by("-c"))
    channels = list(tickets.values("channel").annotate(c=Count("id")).order_by("-c")[:15])
    weekly = list(
        tickets.exclude(created_at_external=None)
        .annotate(week=TruncWeek("created_at_external"))
        .values("week")
        .annotate(c=Count("id"))
        .order_by("week")
    )

    thread_lengths = list(messages.values("ticket_id").annotate(c=Count("id")).values_list("c", flat=True))
    avg_thread = (sum(thread_lengths) / len(thread_lengths)) if thread_lengths else 0

    autoresponder_rate = 0.0
    agent_msgs = messages.filter(author_type="AGENT").count()
    if agent_msgs:
        autoresponder_rate = messages.filter(author_type="AGENT", is_autoresponder=True).count() / agent_msgs

    macros = Source.objects.filter(team=team, source_type=SourceType.MACRO, is_active=True)
    macro_usage = list(macros.order_by("-usage_count").values("title", "usage_count")[:20])
    unused_180 = macros.filter(Q(last_used_at__lt=now - timedelta(days=180)) | Q(usage_count=0)).count()

    return {
        "generated_at": now.isoformat(),
        "ticket_count": tickets.count(),
        "message_count": messages.count(),
        "support_count": tickets.filter(qualification="SUPPORT").count(),
        "qualification": qualification,
        "channels": channels,
        "weekly_volume": [
            {"week": (row["week"].isoformat() if row["week"] else None), "count": row["c"]} for row in weekly
        ],
        "avg_thread_length": round(avg_thread, 2),
        "autoresponder_rate": round(autoresponder_rate, 3),
        "resolving_reply_count": messages.filter(is_resolving_reply=True).count(),
        "macro_count": macros.count(),
        "macro_usage_top20": macro_usage,
        "macros_unused_or_never": unused_180,
        "help_center_count": Source.objects.filter(
            team=team, source_type=SourceType.HELP_CENTER_ARTICLE, is_active=True
        ).count(),
        "web_page_count": Source.objects.filter(team=team, source_type=SourceType.WEB_PAGE, is_active=True).count(),
        "qualifier_versions": list(tickets.values("qualifier_version").annotate(c=Count("id")).order_by("-c")),
    }
