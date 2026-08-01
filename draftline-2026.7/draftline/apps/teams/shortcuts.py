from django.http import Http404
from django.shortcuts import get_object_or_404

from apps.teams.context import get_current_team


def get_team_object_or_404(model_class, *args, **kwargs):
    """get_object_or_404 scoped to the current team context.

    Resolves the team from the global team context (set by the team
    middleware on web requests and `set_current_team()` in Celery tasks).
    Raises Http404 if no team is in context.

    Use this instead of `get_object_or_404(MyTeamModel, ...)` to avoid
    cross-team lookups via the unfiltered default manager. Equivalent to
    `get_object_or_404(MyTeamModel.for_team, ...)` but with an API that
    matches Django's stock shortcut.
    """
    team = get_current_team()
    if team is None:
        raise Http404("No team in context")
    explicit_team = kwargs.pop("team", team)
    if explicit_team != team:
        raise ValueError(f"Passed team {explicit_team} does not match the current team context {team}")
    return get_object_or_404(model_class, *args, team=team, **kwargs)
