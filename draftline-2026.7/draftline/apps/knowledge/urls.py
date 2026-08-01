from django.urls import path

from apps.knowledge import views

app_name = "knowledge"

urlpatterns = [
    path("sources/", views.sources_home, name="sources_home"),
    path("sources/tickets/", views.tickets_browser, name="tickets_browser"),
    path("sources/tickets/<int:ticket_id>/", views.ticket_detail, name="ticket_detail"),
    path("sources/<str:source_type>/", views.sources_list, name="sources_list"),
    path("sources/item/<int:source_id>/", views.source_detail, name="source_detail"),
    path("sources/sync/<int:connection_id>/", views.sync_sources, name="sync_sources"),
    path("corpus-report/", views.corpus_report, name="corpus_report"),
]

team_urlpatterns = (urlpatterns, "knowledge")
