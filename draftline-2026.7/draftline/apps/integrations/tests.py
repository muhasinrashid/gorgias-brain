from unittest.mock import MagicMock, patch

import httpx
from django.test import TestCase

from apps.integrations.models import Connection, Provider
from apps.integrations.providers.gorgias.adapter import GorgiasAdapter
from apps.teams.models import Team
from apps.tickets.services.normalisation import classify_author, normalise_message_body


class CredentialSerializationTests(TestCase):
    def test_connection_never_serialises_secrets(self):
        team = Team.objects.create(name="T", slug="t-cred")
        conn = Connection(team=team, provider=Provider.GORGIAS, display_name="g")
        conn.set_credentials({"api_key": "super-secret", "username": "u@x.com"})
        conn.save()
        public = conn.to_public_dict()
        self.assertNotIn("super-secret", str(public))
        decrypted = conn.get_credentials()
        self.assertEqual(decrypted["api_key"], "super-secret")


class NormalisationTests(TestCase):
    def test_from_agent_preferred(self):
        author, direction = classify_author({"from_agent": True, "sender": {"type": "unknown"}})
        self.assertEqual(author, "AGENT")
        self.assertEqual(direction, "OUTBOUND")

    def test_html_strip(self):
        text = normalise_message_body(body_html="<p>Hello <b>world</b></p>")
        self.assertIn("Hello", text)
        self.assertIn("world", text)


def _response(status_code: int, *, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status_code, headers=headers or {}, json={"data": []})


class GorgiasRateLimitTests(TestCase):
    def setUp(self):
        self.adapter = GorgiasAdapter(base_url="https://x.gorgias.com", username="u@x.com", api_key="k")

    def tearDown(self):
        self.adapter.close()

    @patch("apps.integrations.providers.gorgias.adapter.time.sleep")
    def test_429_is_retried_until_success(self, sleep):
        self.adapter._client.request = MagicMock(
            side_effect=[_response(429, headers={"Retry-After": "3"}), _response(200)]
        )
        response = self.adapter._get("/api/tickets")
        self.assertEqual(response.status_code, 200)
        sleep.assert_called_once_with(3.0)

    @patch("apps.integrations.providers.gorgias.adapter.time.sleep")
    def test_retries_are_capped(self, sleep):
        self.adapter._client.request = MagicMock(return_value=_response(429))
        response = self.adapter._get("/api/tickets")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.adapter._client.request.call_count, 6)  # initial + MAX_RETRIES
        self.assertEqual(sleep.call_count, 5)

    @patch("apps.integrations.providers.gorgias.adapter.time.sleep")
    def test_client_errors_are_not_retried(self, sleep):
        self.adapter._client.request = MagicMock(return_value=_response(404))
        response = self.adapter._get("/api/tickets/1")
        self.assertEqual(response.status_code, 404)
        sleep.assert_not_called()
