from datetime import date, datetime, timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.template.response import TemplateResponse
from django.utils import timezone

from apps.dashboard.forms import DateRangeForm
from apps.dashboard.services import get_user_signups
from apps.users.models import CustomUser


def _string_to_date(date_str: str | None, default: date) -> date:
    date_format = "%Y-%m-%d"
    if not date_str:
        return default
    try:
        return datetime.strptime(date_str, date_format).date()
    except ValueError:
        return default


@user_passes_test(lambda u: u.is_superuser, login_url="/404")
@staff_member_required
def dashboard(request):
    end = _string_to_date(request.GET.get("end"), timezone.now().date() + timedelta(days=1))
    start = _string_to_date(request.GET.get("start"), end - timedelta(days=90))
    form = DateRangeForm(initial={"start": start, "end": end})
    start_value = CustomUser.objects.filter(date_joined__lt=start).count()
    return TemplateResponse(
        request,
        "dashboard/user_dashboard.html",
        context={
            "active_tab": "project-dashboard",
            "signup_data": get_user_signups(start, end),
            "form": form,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "start_value": start_value,
        },
    )
