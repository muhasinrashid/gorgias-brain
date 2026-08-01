from django.shortcuts import redirect, render
from django.urls import reverse

from apps.agents.models import Agent, AgentStatus
from apps.billing.services import get_entitlement
from apps.integrations.models import Connection
from apps.teams.decorators import login_and_team_required


@login_and_team_required
def agent_home(request, team_slug):
    team = request.team
    agents = Agent.objects.filter(team=team).order_by("created_at")
    agent = agents.first()
    if agent is None:
        agent = Agent.objects.create(
            team=team,
            name="Support Agent",
            status=AgentStatus.DRAFT,
            created_by=request.user,
            shadow_mode=True,
        )
    connections = Connection.objects.filter(team=team)
    entitlement = get_entitlement(team)
    checklist = {
        "has_connection": connections.exists(),
        "has_healthy_connection": connections.filter(status="HEALTHY").exists(),
        "agent_configured": bool(agent.current_instructions.strip()),
        "entitlement_active": entitlement.is_active(),
    }
    return render(
        request,
        "agents/home.html",
        {
            "agent": agent,
            "agents": agents,
            "connections": connections,
            "entitlement": entitlement,
            "checklist": checklist,
            "active_tab": "agent_home",
            "page_title": "Home",
        },
    )


@login_and_team_required
def agent_activity(request, team_slug):
    agent = Agent.objects.filter(team=request.team).first()
    return render(
        request,
        "agents/activity.html",
        {"agent": agent, "active_tab": "agent_activity", "page_title": "Activity"},
    )


@login_and_team_required
def agent_reports(request, team_slug):
    agent = Agent.objects.filter(team=request.team).first()
    return render(
        request,
        "agents/reports.html",
        {"agent": agent, "active_tab": "agent_reports", "page_title": "Reports"},
    )


@login_and_team_required
def agent_instructions(request, team_slug):
    agent = Agent.objects.filter(team=request.team).order_by("created_at").first()
    if agent is None:
        agent = Agent.objects.create(
            team=request.team,
            name="Support Agent",
            status=AgentStatus.DRAFT,
            created_by=request.user,
            shadow_mode=True,
        )
    if request.method == "POST":
        agent.current_instructions = request.POST.get("instructions", "")
        agent.save(update_fields=["current_instructions", "updated_at"])
        from apps.audit.services import record_audit

        record_audit(
            team=request.team,
            actor=request.user,
            action="agent.instructions_updated",
            object_type="Agent",
            object_id=str(agent.pk),
        )
        return redirect(reverse("agents:instructions", args=[team_slug]))
    return render(
        request,
        "agents/instructions.html",
        {"agent": agent, "active_tab": "agent_instructions", "page_title": "Instructions"},
    )


@login_and_team_required
def agent_settings(request, team_slug):
    agent = Agent.objects.filter(team=request.team).order_by("created_at").first()
    if agent is None:
        agent = Agent.objects.create(
            team=request.team,
            name="Support Agent",
            status=AgentStatus.DRAFT,
            created_by=request.user,
            shadow_mode=True,
        )
    if request.method == "POST":
        agent.kill_switch = request.POST.get("kill_switch") == "on"
        agent.shadow_mode = request.POST.get("shadow_mode") == "on"
        if request.POST.get("activate") == "1":
            agent.status = AgentStatus.ACTIVE
        agent.save()
        from apps.audit.services import record_audit

        record_audit(
            team=request.team,
            actor=request.user,
            action="agent.settings_updated",
            object_type="Agent",
            object_id=str(agent.pk),
            metadata={"kill_switch": agent.kill_switch, "shadow_mode": agent.shadow_mode},
        )
        return redirect(reverse("agents:settings", args=[team_slug]))
    return render(
        request,
        "agents/settings.html",
        {"agent": agent, "active_tab": "agent_settings", "page_title": "Settings"},
    )
