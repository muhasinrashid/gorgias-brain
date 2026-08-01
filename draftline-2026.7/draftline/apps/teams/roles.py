from __future__ import annotations

from django.contrib.auth.models import AnonymousUser

from apps.users.models import CustomUser

ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_AGENT = "agent"
ROLE_VIEWER = "viewer"

# Backward compatibility with Pegasus code that imports ROLE_MEMBER
ROLE_MEMBER = ROLE_AGENT

ROLE_CHOICES = (
    (ROLE_OWNER, "Owner"),
    (ROLE_ADMIN, "Administrator"),
    (ROLE_AGENT, "Agent"),
    (ROLE_VIEWER, "Viewer"),
)

ADMIN_ROLES = frozenset({ROLE_OWNER, ROLE_ADMIN})


def is_member(user: CustomUser | AnonymousUser, team) -> bool:
    if not user.is_authenticated:
        return False
    if not team:
        return False
    return team.members.filter(id=user.id).exists()


def is_admin(user: CustomUser | AnonymousUser, team) -> bool:
    """Owner and Admin may manage connections and instructions."""
    if not user.is_authenticated:
        return False
    if not team:
        return False

    from .models import Membership

    return Membership.objects.filter(team=team, user=user, role__in=ADMIN_ROLES).exists()


def is_owner(user: CustomUser | AnonymousUser, team) -> bool:
    if not user.is_authenticated or not team:
        return False
    from .models import Membership

    return Membership.objects.filter(team=team, user=user, role=ROLE_OWNER).exists()
