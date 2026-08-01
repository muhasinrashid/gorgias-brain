"""Isolation suite — team A must never reach team B data."""

from django.apps import apps
from django.test import Client, TestCase

from apps.agents.models import Agent
from apps.integrations.models import Connection, Provider
from apps.teams.models import Membership, Team
from apps.teams.roles import ROLE_ADMIN, ROLE_OWNER
from apps.tickets.models import Ticket
from apps.users.models import CustomUser

TEAM_SCOPED_APP_LABELS = {"agents", "integrations", "tickets", "audit", "billing"}


class DomainModelsHaveTeamFKTests(TestCase):
    def test_domain_models_are_team_scoped(self):
        """Every concrete domain model in our apps must have a team relation."""
        missing = []
        for model in apps.get_models():
            if model._meta.app_label not in TEAM_SCOPED_APP_LABELS:
                continue
            if model._meta.proxy or model._meta.abstract:
                continue
            field_names = {f.name for f in model._meta.get_fields()}
            if "team" not in field_names:
                missing.append(f"{model._meta.label}")
        self.assertEqual(missing, [], f"Untenanted domain models: {missing}")


class CrossTeamIsolationTests(TestCase):
    def setUp(self):
        self.user_a = CustomUser.objects.create_user(username="a@example.com", email="a@example.com", password="x")
        self.user_b = CustomUser.objects.create_user(username="b@example.com", email="b@example.com", password="x")
        self.team_a = Team.objects.create(name="Team A", slug="team-a")
        self.team_b = Team.objects.create(name="Team B", slug="team-b")
        Membership.objects.create(team=self.team_a, user=self.user_a, role=ROLE_OWNER)
        Membership.objects.create(team=self.team_b, user=self.user_b, role=ROLE_ADMIN)

        self.agent_a = Agent.objects.create(team=self.team_a, name="A")
        self.agent_b = Agent.objects.create(team=self.team_b, name="B")
        self.conn_a = Connection.objects.create(team=self.team_a, provider=Provider.GORGIAS, display_name="ga")
        self.conn_b = Connection.objects.create(team=self.team_b, provider=Provider.GORGIAS, display_name="gb")
        self.ticket_a = Ticket.objects.create(
            team=self.team_a, connection=self.conn_a, external_id="1", subject="A"
        )
        self.ticket_b = Ticket.objects.create(
            team=self.team_b, connection=self.conn_b, external_id="1", subject="B"
        )

    def test_orm_filter_by_team(self):
        self.assertEqual(Agent.objects.filter(team=self.team_a).count(), 1)
        self.assertFalse(Agent.objects.filter(team=self.team_a, pk=self.agent_b.pk).exists())
        self.assertFalse(Ticket.objects.filter(team=self.team_a, pk=self.ticket_b.pk).exists())

    def test_view_isolation(self):
        client = Client()
        client.force_login(self.user_a)
        # User A cannot open team B agent home
        response = client.get(f"/a/{self.team_b.slug}/agent/")
        self.assertIn(response.status_code, (302, 403, 404))

    def test_connection_public_dict_excludes_credentials(self):
        self.conn_a.set_credentials({"api_key": "secret-key", "username": "u"})
        self.conn_a.save()
        public = self.conn_a.to_public_dict()
        blob = str(public)
        self.assertNotIn("secret-key", blob)
        self.assertNotIn("credentials", public)
        self.assertNotIn("credentials_encrypted", public)
