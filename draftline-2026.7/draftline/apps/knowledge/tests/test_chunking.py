from django.test import TestCase

from apps.integrations.models import Connection, ConnectionStatus, Provider
from apps.knowledge.models import Chunk, Source, SourceType
from apps.knowledge.services.chunking import chunk_source, split_text
from apps.teams.models import Team


class SplitTextTests(TestCase):
    def test_short_text_single_span(self):
        spans = split_text("hello world")
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0][2], "hello world")

    def test_long_text_overlaps(self):
        text = ("Paragraph one. " * 80) + ("\n\nParagraph two. " * 80)
        spans = split_text(text, chunk_size=200, overlap=40)
        self.assertGreater(len(spans), 1)
        # offsets should be monotonic starts
        starts = [s[0] for s in spans]
        self.assertEqual(starts, sorted(starts))


class ChunkSourceTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Chunk Team", slug="chunk-team")
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
            external_id="web:test",
            title="FAQ",
            normalised_content=("Returns policy. " * 120) + "\n\n" + ("Shipping policy. " * 120),
        )

    def test_chunk_source_creates_rows(self):
        n = chunk_source(self.source)
        self.assertGreater(n, 0)
        self.assertEqual(Chunk.objects.filter(source=self.source).count(), n)
        # replace is idempotent in count sense
        n2 = chunk_source(self.source)
        self.assertEqual(Chunk.objects.filter(source=self.source).count(), n2)
