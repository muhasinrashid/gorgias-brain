from django.test import TestCase

from apps.integrations.adapters.helpdesk import TicketPayload
from apps.integrations.models import Connection, ConnectionStatus, Provider
from apps.teams.models import Team
from apps.tickets.models import TicketMessage
from apps.tickets.tasks import upsert_messages, upsert_ticket_from_payload


class UpsertLengthTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Limits", slug="limits-team")
        self.connection = Connection.objects.create(
            team=self.team,
            provider=Provider.GORGIAS,
            display_name="G",
            status=ConnectionStatus.HEALTHY,
        )

    def test_oversized_subject_is_truncated(self):
        payload = TicketPayload(
            external_id="1",
            subject="x" * 900,
            status="closed",
            channel="email",
            customer_email="",
            customer_external_id="",
            created_at=None,
            closed_at=None,
            raw={},
        )
        ticket = upsert_ticket_from_payload(team=self.team, connection=self.connection, payload=payload)
        ticket.refresh_from_db()
        self.assertEqual(len(ticket.subject), 512)

    def test_oversized_author_name_is_truncated(self):
        payload = TicketPayload(
            external_id="2",
            subject="hi",
            status="closed",
            channel="email",
            customer_email="",
            customer_external_id="",
            created_at=None,
            closed_at=None,
            raw={},
        )
        ticket = upsert_ticket_from_payload(team=self.team, connection=self.connection, payload=payload)
        upsert_messages(
            team=self.team,
            ticket=ticket,
            raw_messages=[{"id": "m1", "sender": {"name": "n" * 400}, "body_text": "hello"}],
        )
        message = TicketMessage.objects.get(team=self.team, external_id="m1")
        self.assertEqual(len(message.author_name), 255)
