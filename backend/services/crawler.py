import httpx
from bs4 import BeautifulSoup
from backend.services.pii_scrubber import PIIService
from backend.services.vector_store import VectorService

class CrawlerService:
    def __init__(self):
        self.pii_scrubber = PIIService()
        self.vector_service = VectorService()
        self.client = httpx.Client(timeout=10.0, follow_redirects=True)

    def crawl_and_ingest(self, start_url: str, org_id: int):
        """
        Crawls a single URL (e.g. FAQ page), scrubs it, and vectorizes it.
        For MVP, this is a single-page fetch. Can be expanded to recursive crawling.
        """
        try:
            response = self.client.get(start_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract main content - naive implementation
            # Ideally try to find 'main', 'article', or just body
            content = ""
            main_tag = soup.find('main') or soup.find('article') or soup.body
            
            if main_tag:
                # Get text, strip whitespace
                paragraphs = [p.get_text().strip() for p in main_tag.find_all(['p', 'h1', 'h2', 'h3', 'li'])]
                content = "\n".join([p for p in paragraphs if p])
            
            if not content:
                return {"status": "skipped", "reason": "No content found"}

            # PII Scrubbing
            scrubbed_content = self.pii_scrubber.scrub(content)
            
            # Chunking strategies are important for long pages
            # For MVP, we'll store the whole page content or split by heavy headers if needed.
            # Let's verify length. Embedding models have token limits (8191 for text-embedding-3-small).
            # Simple recursive splitter logic is good, but for now let's just create one chunk or truncate.
            # Assuming pages are reasonable FAQ size.
            
            metadata = [{
                "org_id": org_id,
                "source_id": start_url,
                "source_type": "web_page",
                "source_url": start_url
            }]
            
            namespace = f"org_{org_id}"
            self.vector_service.embed_and_store([scrubbed_content], metadata, namespace=namespace)
            
            return {"status": "success", "url": start_url}

        except Exception as e:
            return {"status": "error", "message": str(e)}
