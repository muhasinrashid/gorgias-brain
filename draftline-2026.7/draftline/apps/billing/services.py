from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from django.db import transaction
from django.utils import timezone

from apps.billing.models import (
    BillingProviderCode,
    EntitlementStatus,
    PlanCode,
    TeamEntitlement,
)
from apps.teams.models import Team


@dataclass(frozen=True)
class CheckoutSession:
    url: str
    provider_ref: str


class BillingProvider(Protocol):
    def create_checkout(self, team: Team, plan_code: str) -> CheckoutSession: ...

    def sync_entitlement(self, team: Team) -> TeamEntitlement: ...

    def handle_webhook(self, payload: dict) -> None: ...


DEFAULT_PLAN_QUOTAS: dict[str, int] = {
    PlanCode.TRIAL: 100,
    PlanCode.TEAM: 1000,
    PlanCode.BUSINESS: 5000,
    PlanCode.CUSTOM: 10000,
    PlanCode.INTERNAL: 100000,
}


class ManualBillingProvider:
    """Default billing provider: admin assigns plans offline. No payment gateway."""

    def create_checkout(self, team: Team, plan_code: str) -> CheckoutSession:
        entitlement = self.assign_plan(team, plan_code)
        return CheckoutSession(url="", provider_ref=f"manual:{entitlement.pk}")

    def sync_entitlement(self, team: Team) -> TeamEntitlement:
        entitlement, _ = TeamEntitlement.objects.get_or_create(
            team=team,
            defaults={
                "plan_code": PlanCode.TRIAL,
                "interactions_included": DEFAULT_PLAN_QUOTAS[PlanCode.TRIAL],
                "billing_provider": BillingProviderCode.MANUAL,
                "status": EntitlementStatus.ACTIVE,
            },
        )
        return entitlement

    def handle_webhook(self, payload: dict) -> None:
        return None

    @transaction.atomic
    def assign_plan(self, team: Team, plan_code: str, *, notes: str = "") -> TeamEntitlement:
        if plan_code not in PlanCode.values:
            raise ValueError(f"Unknown plan_code: {plan_code}")
        entitlement = self.sync_entitlement(team)
        entitlement.plan_code = plan_code
        entitlement.interactions_included = DEFAULT_PLAN_QUOTAS.get(plan_code, 100)
        entitlement.interactions_used = 0
        entitlement.period_start = timezone.now()
        entitlement.status = EntitlementStatus.ACTIVE
        entitlement.billing_provider = BillingProviderCode.MANUAL
        if notes:
            entitlement.notes = notes
        entitlement.save()
        return entitlement


def get_entitlement(team: Team) -> TeamEntitlement:
    """Only gateway for feature gates. Never query Stripe/dj-stripe here."""
    return ManualBillingProvider().sync_entitlement(team)


def team_may_draft(team: Team) -> bool:
    return get_entitlement(team).can_consume_interaction()


@transaction.atomic
def consume_interaction(team: Team) -> TeamEntitlement:
    entitlement = TeamEntitlement.objects.select_for_update().get(team=team)
    if not entitlement.can_consume_interaction():
        raise PermissionError("Interaction quota exhausted")
    entitlement.interactions_used += 1
    entitlement.save(update_fields=["interactions_used", "updated_at"])
    return entitlement
