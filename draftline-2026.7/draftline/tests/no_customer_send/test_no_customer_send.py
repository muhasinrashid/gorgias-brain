"""No customer-send capability may exist in the codebase."""

import ast
import inspect
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from apps.integrations.providers.gorgias import adapter as gorgias_adapter
from apps.integrations.providers.gorgias.adapter import (
    ALLOWED_MESSAGE_CHANNELS,
    build_internal_note_payload,
)
from apps.integrations.views import normalize_gorgias_subdomain


class InternalNotePayloadTests(TestCase):
    def test_payload_is_internal_note_only(self):
        payload = build_internal_note_payload("agent@example.com", "Draft body")
        self.assertEqual(payload["channel"], "internal-note")
        self.assertIn(payload["channel"], ALLOWED_MESSAGE_CHANNELS)
        self.assertNotIn(payload["channel"], {"email", "sms", "chat", "facebook", "instagram", "twitter"})
        self.assertTrue(payload["from_agent"])
        self.assertEqual(payload["via"], "api")

    def test_create_internal_note_source_hardcodes_channel(self):
        source = inspect.getsource(gorgias_adapter.GorgiasAdapter.create_internal_note)
        self.assertIn('"channel": "internal-note"', source)
        # Must not accept a channel parameter
        sig = inspect.signature(gorgias_adapter.GorgiasAdapter.create_internal_note)
        self.assertNotIn("channel", sig.parameters)

    def test_health_check_does_not_use_users_me(self):
        source = inspect.getsource(gorgias_adapter.GorgiasAdapter.health_check)
        # Ignore docstring mentions; assert the actual request path.
        self.assertIn('self._client.get("/api/tickets"', source)
        self.assertNotIn('self._client.get("/api/users/me"', source)


class SubdomainNormalizationTests(SimpleTestCase):
    def test_accepts_variants(self):
        self.assertEqual(normalize_gorgias_subdomain("formexwatch"), "formexwatch")
        self.assertEqual(normalize_gorgias_subdomain("formexwatch.gorgias.com"), "formexwatch")
        self.assertEqual(normalize_gorgias_subdomain("https://formexwatch.gorgias.com/app"), "formexwatch")



class NoCustomerSendSurfaceTests(SimpleTestCase):
    """Static scan of integrations providers for forbidden send helpers."""

    FORBIDDEN_NAMES = {
        "send_message",
        "send_email",
        "send_customer_message",
        "reply_to_customer",
        "create_public_message",
    }

    def test_no_forbidden_send_functions_in_gorgias_provider(self):
        root = Path(gorgias_adapter.__file__).resolve().parent
        found = []
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in self.FORBIDDEN_NAMES:
                    found.append(f"{path.name}:{node.name}")
        self.assertEqual(found, [])
