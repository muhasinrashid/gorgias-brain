from django.test import TestCase

from apps.integrations.models import Connection, ConnectionStatus, Provider
from apps.knowledge.models import Chunk, CuratedKnowledge, CuratedStatus, Source, SourceType
from apps.knowledge.services.citations import resolve_chunk_citation
from apps.knowledge.services.intent_taxonomy import seed_intent_taxonomy
from apps.knowledge.services.language import detect_language
from apps.knowledge.services.retrieval import PRECEDENCE, retrieve
from apps.teams.models import Team


class CitationResolveTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Cite", slug="cite-team")
        self.conn = Connection.objects.create(
            team=self.team,
            provider=Provider.WEBSITE,
            display_name="Web",
            status=ConnectionStatus.HEALTHY,
        )
        body = "AAA " + ("return policy text. " * 20) + " ZZZ"
        self.source = Source.objects.create(
            team=self.team,
            connection=self.conn,
            source_type=SourceType.WEB_PAGE,
            external_id="faq-1",
            title="Can I return my watch?",
            url="https://example.com/faqs/?hcUrl=return",
            normalised_content=body,
            is_active=True,
        )
        start = body.index("return policy")
        end = start + len("return policy text. " * 5)
        self.chunk = Chunk.objects.create(
            team=self.team,
            source=self.source,
            ordinal=0,
            text=body[start:end],
            char_offset_start=start,
            char_offset_end=end,
        )

    def test_citation_resolves(self):
        result = resolve_chunk_citation(self.chunk)
        self.assertTrue(result.ok)


class LanguageDetectTests(TestCase):
    def test_languages(self):
        self.assertEqual(detect_language("Where is my order shipping?"), "en")
        self.assertEqual(detect_language("Können Sie mir bitte helfen mit der Garantie?"), "de")
        self.assertIn(detect_language("Bonjour, merci pour votre commande"), ("fr", "en"))


class IntentTaxonomyTests(TestCase):
    def test_seed_includes_not_support(self):
        team = Team.objects.create(name="Tax", slug="tax-team")
        result = seed_intent_taxonomy(team, include_macros=False, include_web_titles=False)
        self.assertGreaterEqual(result["total"], 10)
        from apps.knowledge.models import IntentNode

        self.assertTrue(IntentNode.objects.filter(team=team, slug="not_support").exists())
        self.assertTrue(IntentNode.objects.filter(team=team, slug="warranty").exists())


class PrecedenceDemoTests(TestCase):
    def test_curated_outranks_web_and_pair_weights(self):
        self.assertGreater(PRECEDENCE["curated"], PRECEDENCE[SourceType.HELP_CENTER_ARTICLE])
        self.assertGreater(PRECEDENCE[SourceType.HELP_CENTER_ARTICLE], PRECEDENCE[SourceType.WEB_PAGE])
        self.assertGreater(PRECEDENCE[SourceType.WEB_PAGE], PRECEDENCE["resolution_pair"])
        self.assertGreater(PRECEDENCE["resolution_pair"], PRECEDENCE["macro_phrasing"])

    def test_retrieve_prefers_curated_over_chunk(self):
        team = Team.objects.create(name="Prec", slug="prec-team")
        conn = Connection.objects.create(
            team=team,
            provider=Provider.WEBSITE,
            display_name="Web",
            status=ConnectionStatus.HEALTHY,
        )
        source = Source.objects.create(
            team=team,
            connection=conn,
            source_type=SourceType.WEB_PAGE,
            external_id="w1",
            title="Shipping FAQ",
            url="https://example.com/faqs/shipping",
            normalised_content="We offer free worldwide shipping on all watch orders.",
            is_active=True,
        )
        Chunk.objects.create(
            team=team,
            source=source,
            ordinal=0,
            text="We offer free worldwide shipping on all watch orders.",
            char_offset_start=0,
            char_offset_end=52,
            language="en",
        )
        CuratedKnowledge.objects.create(
            team=team,
            question="Do I have to pay for shipping?",
            answer="Curated: free worldwide shipping on watches.",
            intent="shipping",
            language="en",
            status=CuratedStatus.APPROVED,
            is_deidentified=True,
        )
        hits = retrieve(team, "Do I have to pay for shipping?", limit=3)
        self.assertTrue(hits)
        self.assertEqual(hits[0].kind, "curated")
