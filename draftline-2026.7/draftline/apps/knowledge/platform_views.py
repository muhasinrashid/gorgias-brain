"""Staff-only platform crawler (Apify) settings."""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.knowledge.models import PlatformCrawlerSettings


@user_passes_test(lambda u: u.is_superuser, login_url="/404")
@staff_member_required
@require_http_methods(["GET", "POST"])
def platform_crawler_settings(request):
    settings_obj = PlatformCrawlerSettings.get_solo()
    if request.method == "POST":
        settings_obj.enabled = request.POST.get("enabled") == "on"
        settings_obj.apify_actor = (request.POST.get("apify_actor") or "").strip()
        try:
            settings_obj.default_max_depth = max(0, int(request.POST.get("default_max_depth") or 2))
            settings_obj.default_max_pages = max(1, int(request.POST.get("default_max_pages") or 30))
            settings_obj.hard_max_pages = max(1, int(request.POST.get("hard_max_pages") or 100))
        except ValueError:
            messages.error(request, "Invalid numeric crawl limits.")
            return redirect("knowledge_platform:crawler_settings")

        new_key = (request.POST.get("apify_api_key") or "").strip()
        if new_key:
            settings_obj.set_apify_api_key(new_key)
        clear_key = request.POST.get("clear_api_key") == "on"
        if clear_key:
            settings_obj.set_apify_api_key("")

        settings_obj.last_error = ""
        settings_obj.save()
        messages.success(request, "Platform crawler settings saved.")
        return redirect("knowledge_platform:crawler_settings")

    return render(
        request,
        "knowledge/platform_crawler_settings.html",
        {
            "settings_obj": settings_obj,
            "masked_key": settings_obj.masked_api_key(),
            "has_key": bool(settings_obj.get_apify_api_key()),
            "active_tab": "platform_crawler",
            "page_title": "Platform crawler",
        },
    )


@user_passes_test(lambda u: u.is_superuser, login_url="/404")
@staff_member_required
@require_http_methods(["POST"])
def platform_crawler_health(request):
    settings_obj = PlatformCrawlerSettings.get_solo()
    key = settings_obj.get_apify_api_key()
    actor = settings_obj.resolve_actor()
    if not key:
        settings_obj.last_error = "No Apify API key configured."
        settings_obj.last_health_check_at = timezone.now()
        settings_obj.save(update_fields=["last_error", "last_health_check_at", "updated_at"])
        messages.error(request, settings_obj.last_error)
        return redirect("knowledge_platform:crawler_settings")
    if not actor:
        settings_obj.last_error = "No Apify actor id configured (paste your custom actor when ready)."
        settings_obj.last_health_check_at = timezone.now()
        settings_obj.save(update_fields=["last_error", "last_health_check_at", "updated_at"])
        messages.warning(request, settings_obj.last_error)
        return redirect("knowledge_platform:crawler_settings")
    try:
        from apify_client import ApifyClient

        client = ApifyClient(key)
        # Cheap auth check — list user
        client.user().get()
        settings_obj.last_error = ""
        settings_obj.last_health_check_at = timezone.now()
        settings_obj.save(update_fields=["last_error", "last_health_check_at", "updated_at"])
        messages.success(request, f"Apify credentials OK. Actor configured: {actor}")
    except Exception as exc:
        settings_obj.last_error = str(exc)
        settings_obj.last_health_check_at = timezone.now()
        settings_obj.save(update_fields=["last_error", "last_health_check_at", "updated_at"])
        messages.error(request, f"Apify check failed: {exc}")
    return redirect("knowledge_platform:crawler_settings")
