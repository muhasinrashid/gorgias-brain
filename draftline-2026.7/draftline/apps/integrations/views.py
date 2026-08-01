from __future__ import annotations

from urllib.parse import urlparse

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.audit.services import record_audit
from apps.integrations.models import Connection, ConnectionStatus, Provider
from apps.integrations.providers.gorgias.adapter import GorgiasAdapter
from apps.integrations.services.sync_status import build_sync_status
from apps.knowledge.services.ingest import ingest_gorgias_sources, ingest_website
from apps.teams.decorators import login_and_team_required, team_admin_required
from apps.tickets.models import Ticket
from apps.tickets.tasks import backfill_gorgias_tickets


def normalize_gorgias_subdomain(raw: str) -> str:
    """Accept subdomain, host, or full URL and return the Gorgias subdomain."""
    value = (raw or "").strip()
    if not value:
        return ""
    if "://" not in value and "/" not in value and " " not in value:
        host = value
    else:
        parsed = urlparse(value if "://" in value else f"https://{value}")
        host = parsed.netloc or parsed.path.split("/")[0]
    host = host.lower().strip(".")
    for suffix in (".gorgias.com", ".gorgias.io"):
        if host.endswith(suffix):
            host = host[: -len(suffix)]
            break
    return host.split("/")[0].strip()


@login_and_team_required
def integrations_list(request, team_slug):
    connections = list(Connection.objects.filter(team=request.team).order_by("provider", "display_name"))
    connection_rows = [{"connection": c, "sync_status": build_sync_status(c)} for c in connections]
    return render(
        request,
        "integrations/list.html",
        {
            "connection_rows": connection_rows,
            "active_tab": "integrations",
            "page_title": "Integrations",
        },
    )


@team_admin_required
def gorgias_connect(request, team_slug):
    team = request.team
    context = {"active_tab": "integrations", "page_title": "Connect Gorgias"}

    if request.method == "POST":
        subdomain = normalize_gorgias_subdomain(request.POST.get("subdomain") or "")
        username = (request.POST.get("username") or "").strip()
        api_key = (request.POST.get("api_key") or "").strip()
        depth = request.POST.get("depth") or "full"
        context.update({"subdomain": subdomain, "username": username, "depth": depth})

        if not subdomain or not username or not api_key:
            context["form_error"] = "Subdomain, username, and API key are required."
            messages.error(request, context["form_error"])
            return render(request, "integrations/gorgias_connect.html", context)

        base_url = f"https://{subdomain}.gorgias.com"
        adapter = GorgiasAdapter(base_url=base_url, username=username, api_key=api_key)
        try:
            ok, err = adapter.health_check()
            if not ok:
                context["form_error"] = err or "Could not authenticate with Gorgias. Check credentials."
                messages.error(request, context["form_error"])
                return render(request, "integrations/gorgias_connect.html", context)

            capabilities = adapter.probe_capabilities()
            connection = Connection(
                team=team,
                provider=Provider.GORGIAS,
                display_name=f"Gorgias ({subdomain})",
                config={"base_url": base_url, "subdomain": subdomain, "depth": depth},
                capabilities={
                    "can_list_tickets": capabilities.can_list_tickets,
                    "can_fetch_messages": capabilities.can_fetch_messages,
                    "can_create_internal_note": capabilities.can_create_internal_note,
                    "can_add_tag": capabilities.can_add_tag,
                    "details": capabilities.details,
                },
                status=ConnectionStatus.PENDING,
                health={"probed": True, "auth_ok": True},
            )
            connection.set_credentials({"username": username, "api_key": api_key, "base_url": base_url})
            connection.save()
            record_audit(
                team=team,
                actor=request.user,
                action="connection.created",
                object_type="Connection",
                object_id=str(connection.pk),
                metadata={"provider": Provider.GORGIAS, "subdomain": subdomain},
            )
            messages.success(request, "Gorgias connected. Importing your tickets…")
            backfill_gorgias_tickets.delay(team.id, connection.id)
            return redirect(reverse("integrations:detail", args=[team_slug, connection.pk]))
        finally:
            adapter.close()

    return render(request, "integrations/gorgias_connect.html", context)


@login_and_team_required
def connection_detail(request, team_slug, connection_id):
    connection = get_object_or_404(Connection, pk=connection_id, team=request.team)
    from django.db.models import Count

    tickets = []
    qualification_breakdown = []
    webhook_url = ""
    if connection.provider == Provider.GORGIAS:
        tickets = Ticket.objects.filter(team=request.team, connection=connection).order_by("-created_at_external")[
            :50
        ]
        qualification_breakdown = list(
            Ticket.objects.filter(team=request.team, connection=connection)
            .values("qualification")
            .annotate(c=Count("id"))
            .order_by("-c")
            .values_list("qualification", "c")
        )
        webhook_path = reverse("gorgias_webhook", args=[request.team.slug, connection.id])
        webhook_url = request.build_absolute_uri(webhook_path)

    sync_status = build_sync_status(connection)
    return render(
        request,
        "integrations/detail.html",
        {
            "connection": connection,
            "sync_status": sync_status,
            "tickets": tickets,
            "qualification_breakdown": qualification_breakdown,
            "webhook_url": webhook_url,
            "active_tab": "integrations",
            "page_title": connection.display_name or "Connection",
        },
    )


@login_and_team_required
@require_GET
def connection_status(request, team_slug, connection_id):
    connection = get_object_or_404(Connection, pk=connection_id, team=request.team)
    return JsonResponse(build_sync_status(connection))


@team_admin_required
def website_connect(request, team_slug):
    from apps.knowledge.models import PlatformCrawlerSettings

    team = request.team
    solo = PlatformCrawlerSettings.get_solo()
    context = {
        "active_tab": "integrations",
        "page_title": "Connect website",
        "max_depth": solo.default_max_depth,
        "max_pages": solo.default_max_pages,
        "hard_max_pages": solo.hard_max_pages,
    }

    if request.method == "POST":
        display_name = (request.POST.get("display_name") or "").strip() or "Website"
        raw_urls = request.POST.get("seed_urls") or ""
        seed_urls = [line.strip() for line in raw_urls.splitlines() if line.strip()]
        try:
            max_depth = int(request.POST.get("max_depth") or solo.default_max_depth)
            max_pages = int(request.POST.get("max_pages") or solo.default_max_pages)
        except ValueError:
            context["form_error"] = "Invalid depth or page limits."
            context.update({"display_name": display_name, "seed_urls": raw_urls})
            return render(request, "integrations/website_connect.html", context)

        max_pages = min(max(1, max_pages), solo.hard_max_pages)
        max_depth = max(0, max_depth)
        context.update(
            {
                "display_name": display_name,
                "seed_urls": raw_urls,
                "max_depth": max_depth,
                "max_pages": max_pages,
            }
        )
        if not seed_urls:
            context["form_error"] = "Add at least one seed URL."
            messages.error(request, context["form_error"])
            return render(request, "integrations/website_connect.html", context)

        connection = Connection(
            team=team,
            provider=Provider.WEBSITE,
            display_name=display_name[:255],
            config={"seed_urls": seed_urls, "max_pages": max_pages, "max_depth": max_depth},
            status=ConnectionStatus.PENDING,
            health={"queued": True, "phase": "CRAWLING", "pages_target": max_pages, "pages_done": 0},
        )
        connection.save()
        record_audit(
            team=team,
            actor=request.user,
            action="connection.created",
            object_type="Connection",
            object_id=str(connection.pk),
            metadata={"provider": Provider.WEBSITE, "seed_count": len(seed_urls)},
        )
        ingest_website.delay(team.id, connection.id)
        messages.success(request, "Website connected. Crawling pages…")
        return redirect(reverse("integrations:detail", args=[team_slug, connection.pk]))

    return render(request, "integrations/website_connect.html", context)


@team_admin_required
@require_POST
def trigger_retry(request, team_slug, connection_id):
    """Customer-facing Try again — queues the right job without ops jargon."""
    connection = get_object_or_404(Connection, pk=connection_id, team=request.team)
    if connection.provider == Provider.GORGIAS:
        from apps.tickets.models import BackfillCheckpoint, SyncPhase

        checkpoint = BackfillCheckpoint.objects.filter(team=request.team, connection=connection).first()
        if checkpoint and checkpoint.phase == SyncPhase.SOURCES and checkpoint.status != "FAILED":
            ingest_gorgias_sources.delay(request.team.id, connection.id)
            messages.info(request, "Resuming knowledge sync…")
        else:
            backfill_gorgias_tickets.delay(request.team.id, connection.id)
            messages.info(request, "Resuming ticket import…")
    elif connection.provider == Provider.WEBSITE:
        ingest_website.delay(request.team.id, connection.id)
        messages.info(request, "Resuming website crawl…")
    else:
        messages.error(request, "This connection cannot be retried yet.")
    return redirect(reverse("integrations:detail", args=[team_slug, connection.pk]))


@team_admin_required
@require_POST
def trigger_website_sync(request, team_slug, connection_id):
    connection = get_object_or_404(Connection, pk=connection_id, team=request.team, provider=Provider.WEBSITE)
    ingest_website.delay(request.team.id, connection.id)
    messages.info(request, "Refreshing website pages…")
    return redirect(reverse("integrations:detail", args=[team_slug, connection.pk]))


@team_admin_required
@require_POST
def trigger_backfill(request, team_slug, connection_id):
    connection = get_object_or_404(Connection, pk=connection_id, team=request.team, provider=Provider.GORGIAS)
    backfill_gorgias_tickets.delay(request.team.id, connection.id)
    messages.info(request, "Refreshing ticket import…")
    return redirect(reverse("integrations:detail", args=[team_slug, connection.pk]))


@team_admin_required
@require_POST
def trigger_source_sync(request, team_slug, connection_id):
    connection = get_object_or_404(Connection, pk=connection_id, team=request.team, provider=Provider.GORGIAS)
    ingest_gorgias_sources.delay(request.team.id, connection.id)
    messages.info(request, "Refreshing macros and help articles…")
    return redirect(reverse("integrations:detail", args=[team_slug, connection.pk]))
