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
    path("curated/", views.curated_list, name="curated_list"),
    path("curated/new/", views.curated_create, name="curated_create"),
    path("curated/<int:curated_id>/", views.curated_detail, name="curated_detail"),
    path("curated/<int:curated_id>/edit/", views.curated_edit, name="curated_edit"),
    path("curated/<int:curated_id>/deidentify/", views.curated_deidentify, name="curated_deidentify"),
    path("curated/<int:curated_id>/approve/", views.curated_approve, name="curated_approve"),
    path("curated/<int:curated_id>/retire/", views.curated_retire, name="curated_retire"),
    path("curated/from-pair/<int:pair_id>/", views.curated_from_pair, name="curated_from_pair"),
]

team_urlpatterns = (urlpatterns, "knowledge")
