from django.urls import path

from apps.knowledge import platform_views

app_name = "knowledge_platform"

urlpatterns = [
    path("crawler/", platform_views.platform_crawler_settings, name="crawler_settings"),
    path("crawler/health/", platform_views.platform_crawler_health, name="crawler_health"),
]
