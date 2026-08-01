"""Celery integration helpers for team-scoped background work."""

import functools
import inspect

from celery import shared_task

from apps.teams.context import current_team
from apps.teams.models import Team


def team_task(*shared_task_args, **shared_task_kwargs):
    """Celery task decorator that runs the task body inside a team context.

    Convention: the task's first parameter (after ``self`` when
    ``bind=True``) is treated as a ``team_id``. It can be passed either
    positionally or as a keyword argument under the parameter's name.
    The decorator loads the team, enters the team context, and invokes
    the body. Inside, queries using the team-scoped ``for_team`` manager
    Just Work.

    Usage::

        @team_task(bind=True, max_retries=2)
        def my_task(self, team_id, other_id):
            obj = SomeTeamScopedModel.for_team.get(pk=other_id)
            ...

        my_task.delay(team.id, payload.id)            # positional
        my_task.delay(team_id=team.id, other_id=...)  # kwarg

    Failures to load the team propagate as ``Team.DoesNotExist`` — this is
    intentional. A task enqueued against a deleted team is a bug, not a
    silent no-op.
    """
    bind = shared_task_kwargs.get("bind", False)
    team_arg_position = 1 if bind else 0

    def decorator(func):
        params = list(inspect.signature(func).parameters)
        team_param_name = params[team_arg_position]

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if len(args) > team_arg_position:
                team_id = args[team_arg_position]
            elif team_param_name in kwargs:
                team_id = kwargs[team_param_name]
            else:
                raise TypeError(
                    f"@team_task expects team_id as positional arg "
                    f"{team_arg_position} or kwarg '{team_param_name}' "
                    f"(got args={args!r}, kwargs={kwargs!r})."
                )
            team = Team.objects.get(pk=team_id)
            with current_team(team):
                return func(*args, **kwargs)

        return shared_task(*shared_task_args, **shared_task_kwargs)(wrapper)

    return decorator
