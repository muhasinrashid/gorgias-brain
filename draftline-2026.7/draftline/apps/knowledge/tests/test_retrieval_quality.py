from django.test import SimpleTestCase

from apps.knowledge.services.retrieval import _detect_intents, _topical_score
from apps.knowledge.services.web_quarantine import classify_web_page


class QuarantineClassificationTests(SimpleTestCase):
    def test_keeps_faq_urls(self):
        self.assertEqual(
            classify_web_page(
                "https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Fcan-i-return-my-watch",
                "Can I return my watch?",
                "Yes. You have 30 days.",
            ),
            "keep",
        )

    def test_drops_collections(self):
        self.assertEqual(
            classify_web_page(
                "https://formexwatch.com/collections/reef-42-mm/",
                "REEF",
                "Buy the Reef 42mm watch.",
            ),
            "drop",
        )

    def test_legal_stays_as_fallback(self):
        self.assertEqual(
            classify_web_page(
                "https://formexwatch.com/terms-of-service",
                "Terms",
                "Our watches are covered by a warranty of three years.",
            ),
            "legal",
        )


class RetrievalTopicalTests(SimpleTestCase):
    def test_return_query_prefers_return_title(self):
        intents = _detect_intents("return policy")
        self.assertIn("return", intents)
        good = _topical_score(intents, "You have 30 days to send your watch back.", "Can I return my watch?")
        bad = _topical_score(intents, "Free worldwide shipping on watches.", "Do I have to pay for shipping?")
        self.assertGreater(good, bad)

    def test_shipping_penalizes_return_title(self):
        intents = _detect_intents("shipping")
        mismatched = _topical_score(
            intents,
            "Return shipping costs are deducted from the refund.",
            "Can I return my watch?",
        )
        matched = _topical_score(
            intents,
            "We offer free worldwide shipping on all watch orders.",
            "Do I have to pay for shipping?",
        )
        self.assertGreater(matched, mismatched)

    def test_warranty_detects_three_year_clause(self):
        intents = _detect_intents("warranty")
        score = _topical_score(
            intents,
            "Our watches are covered by a warranty of three years against manufacturing defects.",
            "Terms of service",
        )
        self.assertGreater(score, 0.2)
