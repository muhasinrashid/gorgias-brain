from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.integrations.models import Connection, ConnectionStatus, Provider
from apps.knowledge.services.ingest import ingest_website
from apps.teams.models import Team
from apps.tickets.tasks import backfill_gorgias_tickets
from apps.utils.locks import lock_cache, single_flight
from apps.utils.tests.test_locks import LOCMEM_LOCKS


@override_settings(CACHES=LOCMEM_LOCKS)
class TaskDedupeTests(TestCase):
    def setUp(self):
        lock_cache().clear()
        self.team = Team.objects.create(name="Dedupe", slug="dedupe-team")
        self.connection = Connection.objects.create(
            team=self.team,
            provider=Provider.GORGIAS,
            display_name="G",
            status=ConnectionStatus.HEALTHY,
        )

    def test_backfill_skips_when_another_run_holds_lock(self):
        with (
            single_flight(f"backfill_gorgias:{self.connection.id}"),
            patch("apps.tickets.tasks._run_backfill") as run,
        ):
            result = backfill_gorgias_tickets.run(self.team.id, self.connection.id)
        self.assertEqual(result, {"skipped": True, "reason": "already running"})
        run.assert_not_called()

    def test_backfill_runs_when_lock_is_free(self):
        with patch("apps.tickets.tasks._run_backfill", return_value={"imported": 3}) as run:
            result = backfill_gorgias_tickets.run(self.team.id, self.connection.id)
        self.assertEqual(result, {"imported": 3})
        run.assert_called_once()

    def test_website_ingest_skips_when_another_run_holds_lock(self):
        with (
            single_flight(f"ingest_website:{self.connection.id}"),
            patch("apps.knowledge.services.ingest._run_website_ingest") as run,
        ):
            result = ingest_website.run(self.team.id, self.connection.id)
        self.assertEqual(result, {"skipped": True, "reason": "already running"})
        run.assert_not_called()
