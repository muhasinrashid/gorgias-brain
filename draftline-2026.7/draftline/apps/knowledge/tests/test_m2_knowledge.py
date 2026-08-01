from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.integrations.models import Connection, ConnectionStatus, Provider
from apps.knowledge.models import Chunk, ResolutionPair, Source, SourceType
from apps.knowledge.services.chunking import chunk_source
from apps.knowledge.services.embed_jobs import embed_chunks
from apps.knowledge.services.resolution_pairs import extract_pair_from_ticket
from apps.knowledge.services.retrieval import retrieve
from apps.teams.models import Team
from apps.tickets.models import AuthorType, MessageDirection, Qualification, Ticket, TicketMessage
from apps.utils.locks import lock_cache
from apps.utils.tests.test_locks import LOCMEM_LOCKS


class ResolutionPairExtractionTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="RP", slug="rp-team")
        self.connection = Connection.objects.create(
            team=self.team,
            provider=Provider.GORGIAS,
            display_name="G",
            status=ConnectionStatus.HEALTHY,
        )
        self.ticket = Ticket.objects.create(
            team=self.team,
            connection=self.connection,
            external_id="99",
            subject="Where is my order?",
            status="closed",
            qualification=Qualification.SUPPORT,
            qualification_confidence=0.9,
        )
        TicketMessage.objects.create(
            team=self.team,
            ticket=self.ticket,
            external_id="m1",
            sequence=0,
            direction=MessageDirection.INBOUND,
            author_type=AuthorType.CUSTOMER,
            normalised_text="Hi, where is my order? Tracking shows nothing.",
        )
        TicketMessage.objects.create(
            team=self.team,
            ticket=self.ticket,
            external_id="m2",
            sequence=1,
            direction=MessageDirection.OUTBOUND,
            author_type=AuthorType.AGENT,
            normalised_text="Your order shipped yesterday via UPS. Tracking: 1Z999. It should arrive in 2-3 days.",
            is_resolving_reply=True,
        )

    def test_extracts_pair(self):
        pair = extract_pair_from_ticket(self.ticket)
        self.assertIsNotNone(pair)
        self.assertIn("order", pair.question_text.lower())
        self.assertIn("UPS", pair.resolution_text)
        self.assertEqual(pair.source_ticket_ids, ["99"])

    def test_skips_low_confidence(self):
        self.ticket.qualification_confidence = 0.2
        self.ticket.save(update_fields=["qualification_confidence"])
        self.assertIsNone(extract_pair_from_ticket(self.ticket))

    def test_idempotent(self):
        extract_pair_from_ticket(self.ticket)
        extract_pair_from_ticket(self.ticket)
        self.assertEqual(ResolutionPair.objects.filter(team=self.team).count(), 1)


@override_settings(CACHES=LOCMEM_LOCKS)
class EmbedChunksTests(TestCase):
    def setUp(self):
        lock_cache().clear()
        self.team = Team.objects.create(name="Emb", slug="emb-team")
        self.connection = Connection.objects.create(
            team=self.team,
            provider=Provider.WEBSITE,
            display_name="W",
            status=ConnectionStatus.HEALTHY,
        )
        self.source = Source.objects.create(
            team=self.team,
            connection=self.connection,
            source_type=SourceType.WEB_PAGE,
            external_id="web:1",
            title="Returns",
            normalised_content="You can return watches within 30 days of delivery.",
        )
        chunk_source(self.source)

    @patch("apps.knowledge.services.embed_jobs.embed_texts")
    @patch("apps.knowledge.services.embed_jobs.embedder_ready", return_value=True)
    def test_embeds_missing_chunks(self, _ready, mock_embed):
        mock_embed.return_value = [[0.1] * 1536]
        result = embed_chunks.run(self.team.id)
        self.assertEqual(result["embedded"], 1)
        chunk = Chunk.objects.get(source=self.source)
        self.assertIsNotNone(chunk.embedding)
        self.assertTrue(chunk.embedder_version)


class RetrievalStubTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Ret", slug="ret-team")
        self.connection = Connection.objects.create(
            team=self.team,
            provider=Provider.WEBSITE,
            display_name="W",
            status=ConnectionStatus.HEALTHY,
        )
        self.source = Source.objects.create(
            team=self.team,
            connection=self.connection,
            source_type=SourceType.WEB_PAGE,
            external_id="web:2",
            title="Shipping",
            normalised_content="Standard shipping takes 3 to 5 business days worldwide.",
            is_active=True,
        )
        chunk_source(self.source)

    @patch("apps.knowledge.services.retrieval.embedder_ready", return_value=False)
    def test_lexical_fallback(self, _ready):
        hits = retrieve(self.team, "shipping", limit=3)
        self.assertTrue(hits)
        self.assertEqual(hits[0].kind, "chunk")
        self.assertEqual(hits[0].source_id, self.source.id)
        self.assertIsNotNone(hits[0].char_offset_start)
