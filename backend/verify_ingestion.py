
import os
import sys
from dotenv import load_dotenv
import json

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.adapters.gorgias import GorgiasAdapter
from backend.services.vector_store import VectorService
from backend.services.pii_scrubber import PIIService

def verify_ingestion():
    # Redirect stdout to a file for debugging
    log_file = open("verification_log.txt", "w")
    original_stdout = sys.stdout
    sys.stdout = log_file
    
    try:
        load_dotenv()
        
        # 1. Check Credentials
        print("\n--- 1. Checking Credentials ---")
        api_key_env = os.getenv("GORGIAS_API_KEY")
        username_env = os.getenv("GORGIAS_USERNAME")
        base_url_env = os.getenv("GORGIAS_BASE_URL")
        
        if not all([api_key_env, username_env, base_url_env]):
            print("Error: Missing Gorgias credentials in .env")
            return

        # Strip whitespace just in case
        api_key = api_key_env.strip()
        username = username_env.strip()
        base_url = base_url_env.strip().rstrip('/')

        print(f"Base URL: {base_url}")
        print(f"Username: {username}")
        print(f"API Key: {api_key[:5]}...[PRESENT]")
    
        # 2. Connect to Gorgias
        print("\n--- 2. Connecting to Gorgias ---")
        adapter = GorgiasAdapter(api_key=api_key, base_url=base_url, username=username)
        
        # Override health check to use list users (since /me is failing with 400 pk error)
        def robust_health_check(adapter):
            try:
                # Try listing users instead of 'me'
                print(f"Attempting health check against: {adapter.client.base_url}/api/users?limit=1")
                response = adapter.client.get("/api/users", params={"limit": 1}, headers=adapter._get_headers())
                if response.status_code == 200:
                    return True
                print(f"Health check failed with status: {response.status_code}")
                print(f"Response: {response.text}")
                return False
            except Exception as e:
                print(f"Health check exception: {e}")
                return False

        if robust_health_check(adapter):
            print("✅ Gorgias Connection Successful")
        else:
            print("❌ Gorgias Connection Failed")
            # Proceed anyway to check if ticket fetching works
    
    
        # 3. Fetch Closed Tickets
        print("\n--- 3. Fetching Closed Tickets ---")
        params = {"limit": 5} # Removing status=closed initially to see if basic fetch works
        try:
            print(f"Fetching tickets with params: {params}")
            tickets = adapter.fetch_tickets(params=params)
            print(f"✅ Successfully fetched {len(tickets)} tickets.")
            
            if tickets:
                print("\nSample Ticket Data:")
                sample = tickets[0]
                print(f"ID: {sample.get('id')}")
                print(f"Subject: {sample.get('subject')}")
                print(f"Created At: {sample.get('created_datetime')}")
        except Exception as e:
            print(f"❌ Failed to fetch tickets: {e}")
            import traceback
            traceback.print_exc(file=log_file)
            return

        # 4. Verify Vector Store / Embedding
        print("\n--- 4. optimizing Vector Embeddings ---")
        try:
            vector_service = VectorService()
            print("✅ VectorService Initialized (Pinecone + Azure OpenAI)")
            
            if tickets:
                print("Attempting to embed sample ticket...")
                pii_scrubber = PIIService()
                
                ticket = tickets[0]
                raw_text = f"Subject: {ticket.get('subject', '')}\nDescription: {ticket.get('description', '')}"
                scrubbed_text = pii_scrubber.scrub(raw_text)
                
                print(f"Original Text Length: {len(raw_text)}")
                print(f"Scrubbed Text Length: {len(scrubbed_text)}")
                
                # Use a test namespace
                namespace = "test_verification_org_0"
                
                metadata = [{
                    "org_id": 0,
                    "source_id": str(ticket.get("id")),
                    "source_type": "gorgias_ticket",
                    "source_url": f"{base_url}/app/ticket/{ticket.get('id')}"
                }]
                
                vector_service.embed_and_store([scrubbed_text], metadata, namespace=namespace)
                print("✅ Sample ticket embedded and stored in Pinecone (namespace='test_verification_org_0')")
            else:
                print("No tickets to embed.")
            
        except Exception as e:
            print(f"❌ Vector Store Verification Failed: {e}")
            import traceback
            traceback.print_exc(file=log_file)
            
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc(file=log_file)
    finally:
        sys.stdout = original_stdout
        log_file.close()

if __name__ == "__main__":
    verify_ingestion()


if __name__ == "__main__":
    verify_ingestion()
