import os
import httpx
from urllib.parse import urlparse
from apify_client import ApifyClient
from backend.services.pii_scrubber import PIIService
from backend.services.vector_store import VectorService


class CrawlerService:
    """
    Generic web crawler service. Designed to work with ANY website URL.
    
    Architecture: Pluggable — currently uses Apify's website-content-crawler,
    but can be swapped for Crawlee, Playwright, or any other crawler by
    implementing the same interface.
    """

    def __init__(self):
        self.pii_scrubber = PIIService()
        self.vector_service = VectorService()
        self.apify_token = os.getenv("APIFY_API_KEY")
        self.client = None
        if self.apify_token:
            self.client = ApifyClient(self.apify_token)

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract the root domain from a URL (e.g. '.example.com')."""
        parsed = urlparse(url)
        return f".{parsed.netloc.lstrip('www.')}"

    @staticmethod
    def _build_glob_patterns(url: str) -> list:
        """Build glob patterns that allow the crawler to follow links
        under the given URL, including query-param based navigation."""
        base = url.rstrip("/")
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        return [
            {"glob": base},
            {"glob": f"{base}/**"},
            {"glob": f"{base}?*"},       # SPA query-param routing (?hcUrl=...)
            {"glob": f"{origin}/**"},     # Broader: anything on the same domain
        ]

    def _build_apify_input(self, start_url: str) -> dict:
        """
        Build a GENERIC Apify run_input that works on any website.
        No domain-specific cookies or selectors — only universal popup handling.
        """
        domain = self._extract_domain(start_url)

        return {
            "startUrls": [{"url": start_url}],
            "maxCrawlDepth": 2,
            "maxCrawlPages": 10,
            "saveHtml": False,
            "saveMarkdown": True,
            # IMPORTANT: True = ignore canonical URL, use actual page URL (prevents dedup skipping)
            # False (default) = use canonical URL for dedup (CAUSES skipping of pages sharing canonicals)
            "useCanonicalUrl": True,
            "keepUrlFragment": True,  # Preserve query params / fragments as distinct pages

            # Generic cookie-consent bypass (common banner names)
            "initialCookies": [
                {"name": "cookieconsent_status", "value": "dismiss", "domain": domain, "path": "/"},
                {"name": "cookie_consent", "value": "accepted", "domain": domain, "path": "/"},
            ],

            # Generic: click common "Accept" / "Close" buttons
            "clickElementsCssSelector": ", ".join([
                "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
                "button[name='accept']",
                ".cookie-accept",
                ".accept-cookies",
                "#accept-cookies",
                ".gl-close-button",          # Global-E
                ".welcome-popup-close",
                "[data-testid='close-button']",
            ]),

            # Generic: remove overlay/modal elements
            "removeElementsCssSelector": ", ".join([
                ".modal-backdrop",
                ".popup",
                ".modal",
                "#CybotCookiebotDialog",
                ".cookie-banner",
                ".global-e-popup-container",
                ".newsletter-popup",
            ]),

            # Scope crawling to same-origin
            "globs": self._build_glob_patterns(start_url),
        }

    def crawl_and_ingest(self, start_url: str, org_id: int):
        """
        Crawls a URL using Apify (or fallback to basic httpx),
        scrubs PII, chunks text, and stores in vector DB.
        
        Works with ANY public website URL.
        """
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        content = ""
        title = start_url

        try:
            if self.client:
                print(f"Using Apify to crawl: {start_url}")
                run_input = self._build_apify_input(start_url)
                
                # Using 'apify/website-content-crawler'
                run = self.client.actor("apify/website-content-crawler").call(run_input=run_input)
                
                # Fetch results from the dataset
                # The actor returns a dataset ID. We fetch items from it.
                dataset = self.client.dataset(run["defaultDatasetId"])
                dataset_items = dataset.list_items().items
                
                if dataset_items:
                    # The actor might return multiple items if multiple pages were crawled (though we set maxCrawlPages=1)
                    # We iterate and concatenate or pick the best one.
                    for item in dataset_items:
                        text_content = item.get("markdown", "") or item.get("text", "")
                        if text_content:
                            content += text_content + "\n\n"
                            # Prefer title from metadata if available
                            if not title or title == start_url:
                                title = item.get("metadata", {}).get("title")
                    
                    print(f"Apify retrieved {len(content)} chars.")
                else:
                    print("Apify run finished but returned no items.")
            
            # Fallback if Apify fails or not configured (though we expect it to be configured now)
            if not content:
                 print("Fallback to simple crawler...")
                 # Simple fallback logic (copied from previous version to keep functionality if key is missing)
                 with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                    response = client.get(start_url)
                    response.raise_for_status()
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(response.text, 'html.parser')
                    for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
                        element.decompose()
                    main_tag = soup.find('main') or soup.find('article') or soup.find('div', class_='content') or soup.body
                    if main_tag:
                        content = main_tag.get_text(separator="\n", strip=True)
                    title = soup.title.string if soup.title else start_url

            if not content:
                 return {"status": "skipped", "reason": "No content found"}

            # PII Scrubbing
            scrubbed_content = self.pii_scrubber.scrub(content)
            
            # Chunking Strategy
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""]
            )
            
            chunks = text_splitter.split_text(scrubbed_content)
            
            print(f"Split content into {len(chunks)} chunks for {start_url}")

            if not chunks:
                 return {"status": "skipped", "reason": "Content too short after splitting"}

            # Prepare metadata
            texts_to_embed = chunks
            metadatas = []
            
            for i, chunk in enumerate(chunks):
                metadatas.append({
                    "org_id": org_id,
                    "source_id": f"{start_url}#chunk{i}",
                    "source_type": "web_page",
                    "source_url": start_url,
                    "title": title,
                    "chunk_index": i
                })
            
            namespace = f"org_{org_id}"
            self.vector_service.embed_and_store(texts_to_embed, metadatas, namespace=namespace)
            
            return {"status": "success", "url": start_url, "chunks_ingested": len(chunks)}

        except Exception as e:
            print(f"Crawling error: {e}")
            return {"status": "error", "message": str(e)}
