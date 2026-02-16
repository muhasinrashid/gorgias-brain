
import os
import sys

# Flush output immediately
sys.stdout.reconfigure(line_buffering=True)

print("--- Start Test ---")

try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ dotenv loaded successfully.")
except ImportError:
    print("❌ Failed to import dotenv.")

try:
    import httpx
    print("✅ httpx imported successfully.")
except ImportError:
    print("❌ Failed to import httpx.")

try:
    from pinecone import Pinecone
    print("✅ pinecone imported successfully.")
except ImportError:
    print("❌ Failed to import pinecone.")
    
try:
    from langchain_openai import OpenAIEmbeddings
    print("✅ langchain_openai imported successfully.")
except ImportError:
    print("❌ Failed to import langchain_openai.")

print("\n--- Testing Connectivity ---")

try:
    api_key = os.getenv("GORGIAS_API_KEY")
    username = os.getenv("GORGIAS_USERNAME")
    base_url = os.getenv("GORGIAS_BASE_URL")
    
    if not all([api_key, username, base_url]):
        print(f"❌ Missing credentials: API={bool(api_key)}, User={bool(username)}, URL={bool(base_url)}")
    else:
        print(f"Testing URL: {base_url}/api/users/me")
        auth = (username, api_key)
        response = httpx.get(f"{base_url}/api/users/me", auth=auth)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            print("✅ Connection Successful!")
        else:
            print(f"❌ Connection Failed: {response.text}")

except Exception as e:
    print(f"❌ Exception: {e}")

print("--- End Test ---")
