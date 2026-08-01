from django.db import models
from django.utils import timezone

from apps.utils.models import BaseModel


class PlanCode(models.TextChoices):
    TRIAL = "TRIAL", "Trial"
    TEAM = "TEAM", "Team"
    BUSINESS = "BUSINESS", "Business"
    CUSTOM = "CUSTOM", "Custom"
    INTERNAL = "INTERNAL", "Internal"


class EntitlementStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    PAST_DUE = "PAST_DUE", "Past due"
    SUSPENDED = "SUSPENDED", "Suspended"
    CANCELLED = "CANCELLED", "Cancelled"


class BillingProviderCode(models.TextChoices):
    MANUAL = "MANUAL", "Manual"
    STRIPE = "STRIPE", "Stripe"
    RAZORPAY = "RAZORPAY", "Razorpay"
    PADDLE = "PADDLE", "Paddle"


class HardCapBehaviour(models.TextChoices):
    BLOCK = "BLOCK", "Block"
    WARN = "WARN", "Warn only"


class TeamEntitlement(BaseModel):
    """Plan and quota for a team. Feature gates read this model — never a payment provider."""

    team = models.OneToOneField("teams.Team", on_delete=models.CASCADE, related_name="entitlement")
    plan_code = models.CharField(max_length=32, choices=PlanCode.choices, default=PlanCode.TRIAL)
    interactions_included = models.PositiveIntegerField(default=100)
    interactions_used = models.PositiveIntegerField(default=0)
    period_start = models.DateTimeField(default=timezone.now)
    period_end = models.DateTimeField(null=True, blank=True)
    overage_packs = models.PositiveIntegerField(default=0)
    hard_cap_behaviour = models.CharField(
        max_length=16, choices=HardCapBehaviour.choices, default=HardCapBehaviour.BLOCK
    )
    status = models.CharField(max_length=16, choices=EntitlementStatus.choices, default=EntitlementStatus.ACTIVE)
    billing_provider = models.CharField(
        max_length=16, choices=BillingProviderCode.choices, default=BillingProviderCode.MANUAL
    )
    provider_ref = models.CharField(max_length=255, blank=True, default="")
    notes = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Team entitlement"
        verbose_name_plural = "Team entitlements"

    def __str__(self) -> str:
        return f"{self.team_id}:{self.plan_code}:{self.status}"

    @property
    def interactions_remaining(self) -> int:
        included = self.interactions_included + (self.overage_packs * 100)
        return max(0, included - self.interactions_used)

    def is_active(self) -> bool:
        return self.status == EntitlementStatus.ACTIVE

    def can_consume_interaction(self) -> bool:
        if not self.is_active():
            return False
        if self.interactions_remaining > 0:
            return True
        return self.hard_cap_behaviour == HardCapBehaviour.WARN
