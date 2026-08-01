from django.urls import path

from apps.integrations import views

app_name = "integrations"

urlpatterns = [
    path("", views.integrations_list, name="list"),
    path("gorgias/connect/", views.gorgias_connect, name="gorgias_connect"),
    path("website/connect/", views.website_connect, name="website_connect"),
    path("<int:connection_id>/", views.connection_detail, name="detail"),
    path("<int:connection_id>/status/", views.connection_status, name="status"),
    path("<int:connection_id>/retry/", views.trigger_retry, name="retry"),
    path("<int:connection_id>/backfill/", views.trigger_backfill, name="backfill"),
    path("<int:connection_id>/sync-sources/", views.trigger_source_sync, name="sync_sources"),
    path("<int:connection_id>/sync-website/", views.trigger_website_sync, name="sync_website"),
]

team_urlpatterns = (urlpatterns, "integrations")
