from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.integrations.models import Connection, ConnectionStatus, Provider
from apps.knowledge.models import PlatformCrawlerSettings, Source, SourceType
from apps.knowledge.services.ingest import upsert_web_page_source
from apps.knowledge.services.web_crawl import (
    APIFY_RUN_TIMEOUT,
    build_draftline_actor_input,
    build_stock_website_content_crawler_input,
    crawl_url_httpx,
    run_field,
)
from apps.teams.models import Team


class WebCrawlInputTests(TestCase):
    def test_draftline_actor_input_keeps_query_globs(self):
        payload = build_draftline_actor_input(
            ["https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Freturns-154421"],
            max_pages=10,
            max_depth=2,
        )
        self.assertEqual(payload["maxCrawlPages"], 10)
        self.assertTrue(any("?*" in p for p in payload["includeUrlPatterns"]))

    def test_stock_actor_input_sets_canonical_true(self):
        payload = build_stock_website_content_crawler_input(
            ["https://formexwatch.com/faqs/"],
            max_pages=5,
            max_depth=1,
        )
        self.assertTrue(payload["useCanonicalUrl"])
        self.assertTrue(payload["keepUrlFragment"])


class ApifyClientCompatTests(TestCase):
    def test_call_kwargs_match_installed_client_signature(self):
        import inspect

        from apify_client import ApifyClient

        signature = inspect.signature(ApifyClient("token").actor("actor").call)
        signature.bind(run_input={}, run_timeout=APIFY_RUN_TIMEOUT)


class RunFieldTests(TestCase):
    def test_reads_pydantic_style_run_object(self):
        class Run:
            id = "abc123"
            default_dataset_id = "ds123"
            status = "SUCCEEDED"

        run = Run()
        self.assertEqual(run_field(run, "id"), "abc123")
        self.assertEqual(run_field(run, "default_dataset_id"), "ds123")
        self.assertEqual(run_field(run, "status"), "SUCCEEDED")

    def test_reads_legacy_camel_case_dict(self):
        run = {"id": "abc123", "defaultDatasetId": "ds123", "status": "SUCCEEDED"}
        self.assertEqual(run_field(run, "id"), "abc123")
        self.assertEqual(run_field(run, "default_dataset_id"), "ds123")

    def test_missing_field_is_empty_string(self):
        self.assertEqual(run_field({}, "default_dataset_id"), "")
        self.assertEqual(run_field(None, "id"), "")


class WebPageUpsertTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="T", slug="web-team")
        self.connection = Connection.objects.create(
            team=self.team,
            provider=Provider.WEBSITE,
            display_name="Site",
            status=ConnectionStatus.HEALTHY,
            config={"seed_urls": ["https://example.com/faq"]},
        )

    def test_upsert_idempotent(self):
        upsert_web_page_source(
            team=self.team,
            connection=self.connection,
            url="https://example.com/faq",
            title="FAQ",
            content="hello",
            metadata={"crawler": "httpx"},
        )
        upsert_web_page_source(
            team=self.team,
            connection=self.connection,
            url="https://example.com/faq",
            title="FAQ updated",
            content="hello world",
            metadata={"crawler": "httpx"},
        )
        self.assertEqual(Source.objects.filter(team=self.team, source_type=SourceType.WEB_PAGE).count(), 1)
        src = Source.objects.get(team=self.team, source_type=SourceType.WEB_PAGE)
        self.assertEqual(src.title, "FAQ updated")
        self.assertIn("hello world", src.normalised_content)


class HttpxFallbackTests(TestCase):
    @patch("apps.knowledge.services.web_crawl.httpx.Client")
    def test_httpx_extracts_main(self, MockClient):
        html = "<html><head><title>T</title></head><body><main>Body copy here</main></body></html>"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value.get.return_value = mock_resp
        mock_cm.__exit__.return_value = None
        MockClient.return_value = mock_cm

        page = crawl_url_httpx("https://example.com/page")
        self.assertIsNotNone(page)
        self.assertEqual(page.title, "T")
        self.assertIn("Body copy here", page.content)
        self.assertEqual(page.crawler, "httpx")


class PlatformCrawlerSettingsTests(TestCase):
    def test_masked_key_and_env_fallback(self):
        solo = PlatformCrawlerSettings.get_solo()
        solo.set_apify_api_key("abcd1234wxyz5678")
        solo.save()
        solo.refresh_from_db()
        masked = solo.masked_api_key()
        self.assertTrue(masked.startswith("abcd"))
        self.assertIn("…", masked)
        self.assertEqual(solo.get_apify_api_key(), "abcd1234wxyz5678")
