from unittest.mock import patch

from django.test import SimpleTestCase

from apps.tickets.models import Qualification
from apps.tickets.services.llm_qualification import LLM_QUALIFIER_VERSION, llm_qualify_ticket
from apps.tickets.services.qualification import HYBRID_QUALIFIER_VERSION, qualify_ticket_hybrid


class HybridQualificationTests(SimpleTestCase):
    def test_rules_short_circuit_social(self):
        with patch("apps.tickets.services.llm_qualification.llm_qualify_ticket") as mock_llm:
            r = qualify_ticket_hybrid(subject="Mention in smooth_bezel's story")
            self.assertEqual(r.qualification, Qualification.SOCIAL_NOTIFICATION)
            mock_llm.assert_not_called()

    def test_unclear_calls_llm(self):
        fake = type(
            "R",
            (),
            {
                "qualification": Qualification.SUPPORT,
                "confidence": 0.91,
                "reason": "llm:azure:customer asking about availability",
                "version": LLM_QUALIFIER_VERSION,
            },
        )()
        with patch("apps.tickets.services.llm_qualification.llm_qualify_ticket", return_value=fake) as mock_llm:
            r = qualify_ticket_hybrid(subject="asdf qwer zxcv weird subject")
            mock_llm.assert_called_once()
            self.assertEqual(r.qualification, Qualification.SUPPORT)
            self.assertEqual(r.version, HYBRID_QUALIFIER_VERSION)

    def test_llm_below_threshold_becomes_unclear(self):
        class FakeClient:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        class Msg:
                            content = '{"qualification":"SUPPORT","confidence":0.4,"reason":"maybe"}'

                        class Choice:
                            message = Msg()

                        class Resp:
                            choices = [Choice()]

                        return Resp()

        with (
            patch("apps.tickets.services.llm_qualification._client_and_model", return_value=(FakeClient(), "m", "azure")),
            patch("django.conf.settings.QUALIFIER_LLM_CONFIDENCE_MIN", 0.8),
            patch("django.conf.settings.QUALIFIER_LLM_SUPPORT_CONFIDENCE_MIN", 0.85),
        ):
            r = llm_qualify_ticket(subject="maybe support?")
            self.assertEqual(r.qualification, Qualification.UNCLEAR)
            self.assertIn("below-threshold", r.reason)
