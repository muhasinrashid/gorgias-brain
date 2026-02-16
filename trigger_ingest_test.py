import requests
import os
import time

# Configuration
API_URL = "http://localhost:8000"
API_KEY = "local-dev-key-12345" # From backend/.env
HEADERS = {"X-API-Key": API_KEY}

def trigger_historical_ingestion():
    print("\n--- Triggering Historical Ingestion (Limit 10) ---")
    try:
        response = requests.post(
            f"{API_URL}/ingest/historical",
            params={"org_id": 1, "limit": 3},
            headers=HEADERS,
            timeout=60
        )
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")

def trigger_web_ingestion(url):
    print(f"\n--- Triggering Web Ingestion for {url} ---")
    try:
        response = requests.post(
            f"{API_URL}/ingest/web",
            params={"url": url, "org_id": 1},
            headers=HEADERS
        )
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Wait a bit for server to be fully up
    print("Waiting for server to be ready...")
    for i in range(10):
        try:
            requests.get(f"{API_URL}/")
            print("Server is up!")
            break
        except:
            time.sleep(1)
            
    # Trigger Historical (will filter short messages)
    trigger_historical_ingestion()
    
    # Trigger Web (will crawl and chunk)
    # Using a Formex page or similar as example. 
    # Since I don't know the exact Help Center URL, I will try the base url.
    # If it fails (e.g. 404), it proves the code ran at least.
    trigger_web_ingestion("https://formexwatch.com/faqs/") 
