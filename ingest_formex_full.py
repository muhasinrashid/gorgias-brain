"""
Script to ingest the full Formex Watch FAQ knowledge base.
Uses the new /ingest/web/batch endpoint to crawl all relevant sections.
"""
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv("backend/.env")

# Default to local dev, but allow override for production via environment variables
API_KEY = os.getenv("ADMIN_API_KEY", "local-dev-key-12345")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip('/')
print(f"Targeting environment: {BASE_URL}")

# List of all key FAQ sections to ingest
# Since they share the same canonical URL https://formexwatch.com/faqs/,
# we must treat them as separate start URLs.
FAQ_URLS = [
    # Main FAQ page
    "https://formexwatch.com/faqs/",
    
    # Returns & Exchanges
    "https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Freturns-154421",
    
    # Shipping
    "https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Fshipping-154418",
    
    # Payment
    "https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Fpayment-154417",
    
    # Gift Options
    "https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Fgift-options-154416",
    
    # Straps & Bezels
    "https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Fstraps-bracelets-and-bezels-154415",
    
    # Technical Questions
    "https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Ftechnical-questions-154414",
    
    # Warranty & Service
    "https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Fwarranty-and-service-154420"
]

def ingest_all():
    print(f"🚀 Starting batch ingestion of {len(FAQ_URLS)} FAQ pages...")
    
    payload = {
        "urls": FAQ_URLS,
        "org_id": 1
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/ingest/web/batch",
            json=payload,
            headers={"X-API-Key": API_KEY},
            timeout=600  # 10 min timeout for batch crawl
        )
        response.raise_for_status()
        
        data = response.json()
        print("\n✅ Batch Ingestion Complete!")
        print(f"Message: {data.get('message')}")
        
        print("\nDetails:")
        for res in data.get("results", []):
            status_icon = "✅" if res.get("status") == "success" else "❌"
            url = res.get("url", "")
            chunks = res.get("chunks_ingested", 0)
            print(f"{status_icon} {url} ({chunks} chunks)")
            
    except Exception as e:
        print(f"\n❌ Error during ingestion: {str(e)}")
        if hasattr(e, 'response') and e.response:
            print(f"Response: {e.response.text}")

if __name__ == "__main__":
    ingest_all()
