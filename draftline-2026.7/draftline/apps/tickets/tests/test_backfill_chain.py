from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.integrations.models import Connection, ConnectionStatus, Provider
from apps.teams.models import Team
from apps.tickets.models import BackfillCheckpoint, SyncPhase
from apps.tickets.tasks import backfill_gorgias_tickets
from apps.utils.locks import lock_cache
from apps.utils.tests.test_locks import LOCMEM_LOCKS


@override_settings(CACHES=LOCMEM_LOCKS)
class BackfillChainTests(TestCase):
    def setUp(self):
        lock_cache().clear()
        self.team = Team.objects.create(name="Chain", slug="chain-team")
        self.connection = Connection.objects.create(
            team=self.team,
            provider=Provider.GORGIAS,
            display_name="G",
            status=ConnectionStatus.PENDING,
            config={"base_url": "https://example.gorgias.com"},
        )

    @patch("apps.knowledge.services.ingest.ingest_gorgias_sources.delay")
    @patch("apps.tickets.tasks.adapter_from_connection")
    def test_ticket_backfill_enqueues_source_sync(self, mock_adapter_factory, mock_delay):
        adapter = mock_adapter_factory.return_value
        page = type("Page", (), {"tickets": [], "next_cursor": None})()
        adapter.list_closed_tickets_page.return_value = page

        result = backfill_gorgias_tickets.run(self.team.id, self.connection.id)
        self.assertEqual(result["phase"], SyncPhase.SOURCES)
        mock_delay.assert_called_once_with(self.team.id, self.connection.id)

        checkpoint = BackfillCheckpoint.objects.get(connection=self.connection)
        self.assertEqual(checkpoint.phase, SyncPhase.SOURCES)
        self.assertEqual(checkpoint.status, "RUNNING")
