from django.test import TestCase

from apps.billing.models import PlanCode, TeamEntitlement
from apps.billing.services import ManualBillingProvider, get_entitlement, team_may_draft
from apps.teams.models import Team


class EntitlementTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="T", slug="t-bill")

    def test_manual_provider_assigns_plan(self):
        provider = ManualBillingProvider()
        entitlement = provider.assign_plan(self.team, PlanCode.TEAM)
        self.assertEqual(entitlement.plan_code, PlanCode.TEAM)
        self.assertEqual(entitlement.interactions_included, 1000)
        self.assertTrue(team_may_draft(self.team))

    def test_get_entitlement_does_not_touch_stripe(self):
        # Creating via get_entitlement must only write TeamEntitlement
        ent = get_entitlement(self.team)
        self.assertIsInstance(ent, TeamEntitlement)
        self.assertEqual(ent.billing_provider, "MANUAL")
        self.assertEqual(TeamEntitlement.objects.filter(team=self.team).count(), 1)
