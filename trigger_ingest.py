import os
import requests
from dotenv import load_dotenv

# Load environment variables from backend/.env
load_dotenv('backend/.env')

# Configuration
API_KEY = os.getenv("ADMIN_API_KEY")
BASE_URL = "https://gorgias-brain-production.up.railway.app"
ORG_ID = 1

if not API_KEY:
    print("❌ Error: ADMIN_API_KEY not found in backend/.env")
    print("Please add ADMIN_API_KEY=your_railway_key to backend/.env")
    exit(1)

print(f"🚀 Triggering ingestion on {BASE_URL}...")

try:
    response = requests.post(
        f"{BASE_URL}/ingest/historical",
        params={"org_id": ORG_ID},
        headers={"X-API-Key": API_KEY},
        timeout=30 # Ingestion might take a bit to start
    )
    
    if response.status_code == 200:
        print("✅ Ingestion Triggered Successfully!")
        print("Response:", response.json())
    else:
        print(f"❌ Failed with Status Code: {response.status_code}")
        print("Response:", response.text)

except Exception as e:
    print(f"💥 Error: {e}")
