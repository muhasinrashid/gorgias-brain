from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.knowledge.models import Source, SourceType
from apps.knowledge.services.ingest import ingest_gorgias_sources
from apps.teams.decorators import login_and_team_required, team_admin_required
from apps.tickets.models import Qualification, Ticket


@login_and_team_required
def sources_home(request, team_slug):
    team = request.team
    counts = {
        "macros": Source.objects.filter(team=team, source_type=SourceType.MACRO, is_active=True).count(),
        "articles": Source.objects.filter(
            team=team, source_type=SourceType.HELP_CENTER_ARTICLE, is_active=True
        ).count(),
        "web_pages": Source.objects.filter(team=team, source_type=SourceType.WEB_PAGE, is_active=True).count(),
        "tickets": Ticket.objects.filter(team=team).count(),
        "support_tickets": Ticket.objects.filter(team=team, qualification=Qualification.SUPPORT).count(),
    }
    return render(
        request,
        "knowledge/sources_home.html",
        {"counts": counts, "active_tab": "sources", "page_title": "Sources"},
    )


@login_and_team_required
def sources_list(request, team_slug, source_type):
    team = request.team
    type_map = {
        "macros": SourceType.MACRO,
        "help-center": SourceType.HELP_CENTER_ARTICLE,
        "web": SourceType.WEB_PAGE,
    }
    st = type_map.get(source_type)
    if not st:
        return redirect(reverse("knowledge:sources_home", args=[team_slug]))
    q = (request.GET.get("q") or "").strip()
    qs = Source.objects.filter(team=team, source_type=st).order_by("-usage_count", "title")
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(normalised_content__icontains=q))
    return render(
        request,
        "knowledge/sources_list.html",
        {
            "sources": qs[:200],
            "source_type": source_type,
            "q": q,
            "active_tab": "sources",
            "page_title": source_type.replace("-", " ").title(),
        },
    )


@login_and_team_required
def source_detail(request, team_slug, source_id):
    source = get_object_or_404(Source, pk=source_id, team=request.team)
    return render(
        request,
        "knowledge/source_detail.html",
        {"source": source, "active_tab": "sources", "page_title": source.title},
    )


@login_and_team_required
def tickets_browser(request, team_slug):
    team = request.team
    q = (request.GET.get("q") or "").strip()
    qualification = (request.GET.get("qualification") or "").strip()
    qs = Ticket.objects.filter(team=team).order_by("-created_at_external", "-id")
    if q:
        qs = qs.filter(Q(subject__icontains=q) | Q(external_id__icontains=q) | Q(customer_email__icontains=q))
    if qualification:
        qs = qs.filter(qualification=qualification)
    breakdown = list(
        Ticket.objects.filter(team=team)
        .values("qualification")
        .annotate(c=Count("id"))
        .order_by("-c")
        .values_list("qualification", "c")
    )
    return render(
        request,
        "knowledge/tickets_browser.html",
        {
            "tickets": qs[:100],
            "q": q,
            "qualification": qualification,
            "qualifications": Qualification.choices,
            "breakdown": breakdown,
            "active_tab": "sources",
            "page_title": "Tickets",
        },
    )


@login_and_team_required
def ticket_detail(request, team_slug, ticket_id):
    ticket = get_object_or_404(Ticket, pk=ticket_id, team=request.team)
    messages = ticket.messages.order_by("sequence", "sent_at", "id")
    return render(
        request,
        "knowledge/ticket_detail.html",
        {"ticket": ticket, "messages": messages, "active_tab": "sources", "page_title": ticket.subject},
    )


@team_admin_required
@require_POST
def sync_sources(request, team_slug, connection_id):
    from apps.integrations.models import Connection

    connection = get_object_or_404(Connection, pk=connection_id, team=request.team)
    ingest_gorgias_sources.delay(request.team.id, connection.id)
    return redirect(reverse("integrations:detail", args=[team_slug, connection.id]))


@login_and_team_required
def corpus_report(request, team_slug):
    from apps.tickets.services.corpus_report import build_corpus_report

    report = build_corpus_report(request.team)
    return render(
        request,
        "knowledge/corpus_report.html",
        {"report": report, "active_tab": "corpus_report", "page_title": "Corpus Report"},
    )
