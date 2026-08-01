from django.test import TestCase
from django.urls import reverse

from apps.knowledge.models import CuratedKnowledge, CuratedStatus
from apps.knowledge.services.deidentify import deidentify_text, still_contains_pii
from apps.knowledge.services.eval_retrieval import (
    EvalQuestion,
    answer_overlap,
    detect_language,
    evaluate_retrieval,
)
from apps.teams.models import Team
from apps.teams.roles import ROLE_ADMIN
from apps.users.models import CustomUser


class DeidentifyTests(TestCase):
    def test_strips_email_and_tracking(self):
        text = "Email jane@formex.com about 1Z999AA10123456784 please."
        cleaned = deidentify_text(text)
        self.assertNotIn("jane@", cleaned)
        self.assertIn("[email]", cleaned)
        self.assertIn("[tracking]", cleaned)
        self.assertFalse(still_contains_pii(cleaned))


class EvalHelpersTests(TestCase):
    def test_overlap_and_language(self):
        self.assertGreater(answer_overlap("return within 30 days unworn", "You can return in 30 days if unworn"), 0.3)
        self.assertEqual(detect_language("Can I return my watch?"), "en")


class CuratedApproveFlowTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Cur", slug="cur-team")
        self.user = CustomUser.objects.create_user(username="admin", email="a@x.com", password="x")
        self.team.members.add(self.user, through_defaults={"role": ROLE_ADMIN})
        self.client.force_login(self.user)

    def test_approve_requires_deid(self):
        item = CuratedKnowledge.objects.create(
            team=self.team,
            question="Returns?",
            answer="Email support@brand.com for returns.",
            status=CuratedStatus.DRAFT,
            is_deidentified=False,
        )
        url = reverse("knowledge:curated_approve", args=[self.team.slug, item.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.status, CuratedStatus.DRAFT)

        deid_url = reverse("knowledge:curated_deidentify", args=[self.team.slug, item.id])
        self.client.post(deid_url)
        item.refresh_from_db()
        self.assertTrue(item.is_deidentified)
        self.client.post(url)
        item.refresh_from_db()
        self.assertEqual(item.status, CuratedStatus.APPROVED)


class EvalRetrievalSmokeTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Ev", slug="ev-team")

    def test_empty_eval(self):
        result = evaluate_retrieval(self.team, [], k=5)
        self.assertEqual(result["n"], 0)
        self.assertEqual(result["recall_at_k"], 0.0)

    def test_question_dataclass_roundtrip_fields(self):
        q = EvalQuestion(
            id="rp-1",
            question="Where is my order?",
            gold_answer="It shipped via UPS yesterday.",
            gold_ticket_ids=["1"],
            language="en",
            pair_id=1,
        )
        self.assertEqual(q.pair_id, 1)
