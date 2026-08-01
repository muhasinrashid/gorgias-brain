from django.test import TestCase
from django.urls import reverse

from apps.integrations.models import Connection, ConnectionStatus, Provider
from apps.integrations.services.sync_status import build_sync_status, friendly_error
from apps.knowledge.models import Source, SourceType
from apps.teams.models import Team
from apps.tickets.models import BackfillCheckpoint, SyncPhase, Ticket
from apps.users.models import CustomUser


class FriendlyErrorTests(TestCase):
    def test_maps_429(self):
        msg = friendly_error("Client error '429 Too Many Requests' for url 'https://x'")
        self.assertIn("slow down", msg.lower())
        self.assertNotIn("429", msg)

    def test_maps_dns(self):
        msg = friendly_error("[Errno -3] Temporary failure in name resolution")
        self.assertIn("could not reach", msg.lower())


class BuildSyncStatusTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Sync Team", slug="sync-team")

    def test_gorgias_running_tickets_phase(self):
        connection = Connection.objects.create(
            team=self.team,
            provider=Provider.GORGIAS,
            display_name="G",
            status=ConnectionStatus.PENDING,
        )
        BackfillCheckpoint.objects.create(
            team=self.team,
            connection=connection,
            status="RUNNING",
            phase=SyncPhase.TICKETS,
            tickets_imported=42,
            pages_scanned=3,
        )
        status = build_sync_status(connection)
        self.assertEqual(status["chip"], "Setting up")
        self.assertTrue(status["running"])
        self.assertTrue(status["poll"])
        self.assertIn("42", status["detail"])
        self.assertEqual(status["progress_mode"], "indeterminate")

    def test_gorgias_ready(self):
        connection = Connection.objects.create(
            team=self.team,
            provider=Provider.GORGIAS,
            display_name="G",
            status=ConnectionStatus.HEALTHY,
        )
        BackfillCheckpoint.objects.create(
            team=self.team,
            connection=connection,
            status="COMPLETED",
            phase=SyncPhase.DONE,
            tickets_imported=10,
        )
        Ticket.objects.create(
            team=self.team,
            connection=connection,
            external_id="1",
            subject="hi",
        )
        Source.objects.create(
            team=self.team,
            connection=connection,
            source_type=SourceType.MACRO,
            external_id="m1",
            title="Macro",
        )
        status = build_sync_status(connection)
        self.assertEqual(status["chip"], "Ready")
        self.assertTrue(status["ready"])
        self.assertFalse(status["poll"])
        self.assertNotIn("api_key", str(status))

    def test_website_determinate_progress(self):
        connection = Connection.objects.create(
            team=self.team,
            provider=Provider.WEBSITE,
            display_name="W",
            status=ConnectionStatus.PENDING,
            config={"max_pages": 20},
            health={"phase": "CRAWLING", "pages_done": 5, "pages_target": 20},
        )
        status = build_sync_status(connection)
        self.assertEqual(status["chip"], "Setting up")
        self.assertEqual(status["progress_mode"], "determinate")
        self.assertEqual(status["progress_pct"], 25)
        self.assertIn("5", status["detail"])

    def test_failed_shows_friendly_error(self):
        connection = Connection.objects.create(
            team=self.team,
            provider=Provider.GORGIAS,
            display_name="G",
            status=ConnectionStatus.ERROR,
            last_error="Client error '429 Too Many Requests' for url 'https://x'",
        )
        BackfillCheckpoint.objects.create(
            team=self.team,
            connection=connection,
            status="FAILED",
            phase=SyncPhase.TICKETS,
        )
        status = build_sync_status(connection)
        self.assertEqual(status["chip"], "Needs attention")
        self.assertTrue(status["failed"])
        self.assertIn("slow down", status["error_message"].lower())


class ConnectionStatusEndpointTests(TestCase):
    def setUp(self):
        from apps.teams.roles import ROLE_ADMIN

        self.team = Team.objects.create(name="API Team", slug="api-team")
        self.user = CustomUser.objects.create_user(username="u", email="u@example.com", password="x")
        self.team.members.add(self.user, through_defaults={"role": ROLE_ADMIN})
        self.connection = Connection.objects.create(
            team=self.team,
            provider=Provider.WEBSITE,
            display_name="Site",
            status=ConnectionStatus.HEALTHY,
            health={"phase": "DONE", "pages_done": 3, "pages_target": 3},
        )

    def test_status_json_is_team_scoped(self):
        self.client.force_login(self.user)
        url = reverse("integrations:status", args=[self.team.slug, self.connection.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["chip"], "Ready")
        self.assertNotIn("credentials", data)
        blob = str(data).lower()
        self.assertNotIn("api_key", blob)
