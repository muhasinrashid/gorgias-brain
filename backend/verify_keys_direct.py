
import os
import sys
import base64
import httpx
from dotenv import load_dotenv

# Try importing Pinecone
try:
    from pinecone import Pinecone
    PINECONE_V3 = True
except ImportError:
    try:
        import pinecone
        PINECONE_V3 = False
    except ImportError:
        print("Error: pinecone-client not installed.")
        # sys.exit(1) # Continue just in case

def verify_keys():
    load_dotenv()
    print("--- Verifying Keys Direct ---")
    
    # 1. Gorgias
    g_api_key = os.getenv("GORGIAS_API_KEY", "").strip()
    g_username = os.getenv("GORGIAS_USERNAME", "").strip()
    g_base_url = os.getenv("GORGIAS_BASE_URL", "").strip().rstrip('/')
    
    print(f"\nGorgias Config:")
    print(f"URL: {g_base_url}")
    print(f"User: {g_username}")
    print(f"Key: {g_api_key[:5]}..." if g_api_key else "Key: MISSING")
    
    if g_api_key and g_username and g_base_url:
        auth_str = f"{g_username}:{g_api_key}"
        auth_bytes = auth_str.encode('ascii')
        base64_bytes = base64.b64encode(auth_bytes)
        base64_auth = base64_bytes.decode('ascii')
        
        headers = {
            "Authorization": f"Basic {base64_auth}",
            "Content-Type": "application/json"
        }
        
        try:
            # Check users
            print(f"Testing connectivity to {g_base_url}/api/users?limit=1...")
            resp = httpx.get(f"{g_base_url}/api/users", params={"limit": 1}, headers=headers, timeout=10)
            if resp.status_code == 200:
                print("✅ Gorgias API Key is CORRECT and connectivity is working.")
                print(f"Sample User email: {resp.json().get('data', [{}])[0].get('email', 'N/A')}")
            else:
                print(f"❌ Gorgias API Key check Failed. Status: {resp.status_code}")
                print(f"Response: {resp.text}")
        except Exception as e:
            print(f"❌ Gorgias Connection Error: {e}")
    else:
        print("❌ Missing Gorgias credentials.")

    # 2. Pinecone
    p_api_key = os.getenv("PINECONE_API_KEY")
    print(f"\nPinecone Config:")
    print(f"Key: {p_api_key[:5]}..." if p_api_key else "Key: MISSING")
    
    if p_api_key:
        try:
            print("Initializing Pinecone client...")
            if PINECONE_V3:
                pc = Pinecone(api_key=p_api_key)
                indexes = pc.list_indexes()
                # v3 list_indexes returns an object, we need to iterate or access
                # It might be an iterable of IndexModel
                names = [idx.name for idx in indexes]
                print(f"✅ Pinecone API Key is CORRECT.")
                print(f"Indexes found: {names}")
            else:
                # pinecone.init(api_key=p_api_key, environment="us-east-1") # Environment is tricky in v2
                # indexes = pinecone.list_indexes()
                print("Skipping check for old pinecone client (assuming failing anyway)")
                
        except Exception as e:
            print(f"❌ Pinecone Error: {e}")
    else:
        print("❌ Missing Pinecone API Key.")

if __name__ == "__main__":
    verify_keys()
