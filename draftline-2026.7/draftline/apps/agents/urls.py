from django.urls import path

from apps.agents import views

app_name = "agents"

urlpatterns = [
    path("", views.agent_home, name="home"),
    path("activity/", views.agent_activity, name="activity"),
    path("reports/", views.agent_reports, name="reports"),
    path("instructions/", views.agent_instructions, name="instructions"),
    path("settings/", views.agent_settings, name="settings"),
]

team_urlpatterns = (urlpatterns, "agents")
