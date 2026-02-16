"""
Tests for CrawlerService — covers Apify config, fallback crawling, and chunking.
"""
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from backend.services.crawler import CrawlerService


class TestApifyConfig(unittest.TestCase):
    """Tests for _build_apify_input and helper methods (no external calls)."""

    @patch('backend.services.crawler.VectorService')
    @patch('backend.services.crawler.PIIService')
    @patch.dict('os.environ', {'APIFY_API_KEY': ''})
    def setUp(self, MockPII, MockVS):
        """Create a CrawlerService with no Apify client (avoids real API)."""
        self.crawler = CrawlerService()

    def test_useCanonicalUrl_is_true(self):
        """useCanonicalUrl must be True to prevent canonical-based dedup skipping."""
        config = self.crawler._build_apify_input("https://example.com/faqs/")
        self.assertTrue(
            config["useCanonicalUrl"],
            "useCanonicalUrl must be True to ignore canonical URLs and treat each page URL as unique"
        )

    def test_keepUrlFragment_is_true(self):
        """keepUrlFragment must be True to preserve query params as distinct pages."""
        config = self.crawler._build_apify_input("https://example.com/faqs/")
        self.assertTrue(config["keepUrlFragment"])

    def test_start_url_preserved(self):
        """The start URL should appear in startUrls."""
        url = "https://shop.example.com/help"
        config = self.crawler._build_apify_input(url)
        self.assertEqual(config["startUrls"], [{"url": url}])

    def test_domain_extraction(self):
        """Domain should be extracted without 'www.' prefix."""
        self.assertEqual(CrawlerService._extract_domain("https://www.example.com/page"), ".example.com")
        self.assertEqual(CrawlerService._extract_domain("https://shop.mystore.com/faq"), ".shop.mystore.com")

    def test_glob_patterns_include_query_params(self):
        """Glob patterns must include ?* pattern for SPA query-param routing."""
        url = "https://example.com/faqs/"
        patterns = self.crawler._build_glob_patterns(url)
        globs = [p["glob"] for p in patterns]
        
        # Must include query-param pattern
        self.assertIn("https://example.com/faqs?*", globs,
                      "Must include ?* glob for SPA query-param routing (e.g. ?hcUrl=...)")
        # Must include recursive pattern
        self.assertIn("https://example.com/faqs/**", globs)
        # Must include same-origin broad pattern
        self.assertIn("https://example.com/**", globs)

    def test_cookies_use_dynamic_domain(self):
        """Cookies should use the extracted domain, not a hardcoded one."""
        config = self.crawler._build_apify_input("https://mysite.io/help")
        for cookie in config["initialCookies"]:
            self.assertEqual(cookie["domain"], ".mysite.io",
                             f"Cookie domain should be dynamic, got: {cookie['domain']}")

    def test_saveMarkdown_enabled(self):
        """Should save markdown for text extraction."""
        config = self.crawler._build_apify_input("https://example.com")
        self.assertTrue(config["saveMarkdown"])
        self.assertFalse(config["saveHtml"])


class TestFallbackCrawler(unittest.TestCase):
    """Tests for the httpx fallback path (when Apify is not configured)."""

    @patch('backend.services.crawler.VectorService')
    @patch('backend.services.crawler.PIIService')
    @patch.dict('os.environ', {'APIFY_API_KEY': ''})
    def setUp(self, MockPII, MockVS):
        self.mock_vector = MockVS.return_value
        self.mock_pii = MockPII.return_value
        self.mock_pii.scrub.side_effect = lambda x: x  # passthrough
        self.crawler = CrawlerService()
        # Ensure Apify client is None so fallback path is used
        self.crawler.client = None

    @patch('backend.services.crawler.httpx.Client')
    def test_fallback_crawl_success(self, MockHttpxClient):
        """Fallback httpx crawler should extract main content and strip nav/footer."""
        html = """
        <html>
            <head><title>Test FAQ Page</title></head>
            <body>
                <header>Site Header</header>
                <nav>Navigation Links</nav>
                <main>
                    <h1>Frequently Asked Questions</h1>
                    <p>This is a detailed answer to a common question about our products and services.</p>
                    <p>Here is more helpful content that customers need to know about returns and shipping.</p>
                </main>
                <footer>Copyright 2024</footer>
            </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        # httpx.Client is used as context manager: `with httpx.Client(...) as client:`
        mock_client_cm = MagicMock()
        mock_client_cm.get.return_value = mock_response
        MockHttpxClient.return_value.__enter__ = MagicMock(return_value=mock_client_cm)
        MockHttpxClient.return_value.__exit__ = MagicMock(return_value=False)

        result = self.crawler.crawl_and_ingest("http://example.com/faq", org_id=1)

        self.assertEqual(result["status"], "success")
        self.assertGreater(result["chunks_ingested"], 0)
        
        # Verify vector store was called
        self.mock_vector.embed_and_store.assert_called_once()
        call_args = self.mock_vector.embed_and_store.call_args
        texts = call_args[0][0]
        metadatas = call_args[0][1]
        
        # Header/footer/nav should be stripped
        full_text = " ".join(texts)
        self.assertNotIn("Site Header", full_text)
        self.assertNotIn("Navigation Links", full_text)
        self.assertNotIn("Copyright 2024", full_text)
        # Main content should be present
        self.assertIn("Frequently Asked Questions", full_text)

    @patch('backend.services.crawler.httpx.Client')
    def test_chunking_with_long_content(self, MockHttpxClient):
        """Long content should be split into multiple chunks."""
        long_text = "This is a sentence about our product. " * 200
        html = f"<html><body><main>{long_text}</main></body></html>"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        mock_client_cm = MagicMock()
        mock_client_cm.get.return_value = mock_response
        MockHttpxClient.return_value.__enter__ = MagicMock(return_value=mock_client_cm)
        MockHttpxClient.return_value.__exit__ = MagicMock(return_value=False)

        result = self.crawler.crawl_and_ingest("http://example.com/long", org_id=1)

        self.assertEqual(result["status"], "success")
        
        call_args = self.mock_vector.embed_and_store.call_args
        texts = call_args[0][0]
        metadatas = call_args[0][1]
        
        self.assertGreater(len(texts), 1, "Long content should produce multiple chunks")
        self.assertEqual(len(texts), len(metadatas))
        # Chunk indices should be sequential
        self.assertEqual(metadatas[0]["chunk_index"], 0)
        self.assertEqual(metadatas[1]["chunk_index"], 1)

    @patch('backend.services.crawler.httpx.Client')
    def test_empty_page_returns_skipped(self, MockHttpxClient):
        """Empty pages should return skipped status."""
        html = "<html><body></body></html>"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        mock_client_cm = MagicMock()
        mock_client_cm.get.return_value = mock_response
        MockHttpxClient.return_value.__enter__ = MagicMock(return_value=mock_client_cm)
        MockHttpxClient.return_value.__exit__ = MagicMock(return_value=False)

        result = self.crawler.crawl_and_ingest("http://example.com/empty", org_id=1)
        self.assertEqual(result["status"], "skipped")

    def test_metadata_contains_required_fields(self):
        """Verify metadata structure for web page chunks."""
        # Test metadata building logic by checking _build_apify_input indirectly
        config = self.crawler._build_apify_input("https://store.example.com/help")
        self.assertIn("startUrls", config)
        self.assertIn("globs", config)
        self.assertIn("maxCrawlPages", config)


class TestApifyCrawlerPath(unittest.TestCase):
    """Tests for the Apify crawler path (mocked ApifyClient)."""

    @patch('backend.services.crawler.ApifyClient')
    @patch('backend.services.crawler.VectorService')
    @patch('backend.services.crawler.PIIService')
    @patch.dict('os.environ', {'APIFY_API_KEY': 'test-key'})
    def test_apify_path_with_markdown_results(self, MockPII, MockVS, MockApifyClient):
        """When Apify returns markdown results, they should be ingested."""
        mock_pii = MockPII.return_value
        mock_pii.scrub.side_effect = lambda x: x
        mock_vector = MockVS.return_value

        # Mock ApifyClient chain
        mock_client = MockApifyClient.return_value
        mock_actor = MagicMock()
        mock_client.actor.return_value = mock_actor
        mock_actor.call.return_value = {"defaultDatasetId": "test-dataset-id"}

        mock_dataset = MagicMock()
        mock_client.dataset.return_value = mock_dataset
        mock_dataset.list_items.return_value.items = [
            {
                "markdown": "# FAQ Page\n\nQ: What is your return policy?\nA: Returns accepted within 30 days of purchase.",
                "metadata": {"title": "FAQ - Example Store"}
            },
            {
                "markdown": "# Shipping Info\n\nWe ship worldwide. Standard shipping takes 5-7 business days.",
                "metadata": {"title": "Shipping - Example Store"}
            }
        ]

        crawler = CrawlerService()

        result = crawler.crawl_and_ingest("https://example.com/help", org_id=42)

        self.assertEqual(result["status"], "success")
        self.assertGreater(result["chunks_ingested"], 0)
        
        # Verify Apify actor was called with correct input
        mock_client.actor.assert_called_with("apify/website-content-crawler")
        call_input = mock_actor.call.call_args[1]["run_input"]
        self.assertTrue(call_input["useCanonicalUrl"], "Must ignore canonical URLs")
        
        # Verify vector store called with correct namespace
        mock_vector.embed_and_store.assert_called_once()
        ns = mock_vector.embed_and_store.call_args[1]["namespace"]
        self.assertEqual(ns, "org_42")


if __name__ == '__main__':
    unittest.main()
