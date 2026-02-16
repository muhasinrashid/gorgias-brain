
import os
import sys

# Add parent to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.adapters.context import get_client_context
from backend.services.pii_scrubber import PIIService
from backend.services.vector_store import VectorService
from backend.database import SessionLocal, engine, Base
from dotenv import load_dotenv

def run_ingestion():
    load_dotenv()
    print("--- Starting Full Ingestion ---")
    
    db = SessionLocal()
    org_id = 1 # Default Org ID, will use Env vars if not in DB due to fallback logic
    
    try:
        # Create Tables if not exist (minimal check)
        # Base.metadata.create_all(bind=engine)
        pass
    except Exception as e:
        print(f"Warning: Could not create tables ({e}). proceed without DB persistence.")

    try:
        # 1. Adapt Context and Fetch
        print(f"Fetching context for Org ID {org_id}...")
        try:
             adapter = get_client_context(org_id, db)
        except ValueError as e:
             print(f"Error getting context: {e}")
             return

        # Fetch tickets
        # Use a reasonable limit for this run
        limit = 50 
        print(f"Fetching up to {limit} tickets...")
        params = {"limit": limit} 
        
        try:
            tickets = adapter.fetch_tickets(params=params)
        except Exception as e:
            print(f"Error fetching tickets: {e}")
            import traceback
            traceback.print_exc()
            return
            
        print(f"✅ Fetched {len(tickets)} tickets.")
        
        if not tickets:
            print("No tickets found to ingest.")
            return

        # 2. Initialize Services
        pii_scrubber = PIIService()
        vector_service = VectorService()
        
        texts_to_embed = []
        metadatas = []
        
        # 3. Process Logic
        print("Processing tickets...")
        for ticket in tickets:
            ticket_id = ticket.get("id")
            subject = ticket.get("subject", "")
            
            # Construct meaningful text representation
            raw_text = f"Subject: {subject}\n" 
            if "description" in ticket and ticket["description"]:
                 raw_text += f"\nDescription: {ticket['description']}"
            else:
                 # Fallback if description is empty or not fetched
                 # Maybe fetch messages? For now, just use subject + placeholder
                 raw_text += "\n(No description provided)"

            # Scrub PII
            scrubbed_text = pii_scrubber.scrub(raw_text)
            
            if not scrubbed_text.strip():
                continue

            # Prepare for Vector Store
            texts_to_embed.append(scrubbed_text)
            
            # Metadata logic
            # Try to get domain from base_url
            try:
                domain = adapter.base_url.replace("https://", "").split(".")[0]
            except:
                domain = "gorgias"
                
            source_url = f"https://{domain}.gorgias.com/app/ticket/{ticket_id}"

            metadatas.append({
                "org_id": org_id,
                "source_id": str(ticket_id),
                "source_type": "gorgias_ticket",
                "source_url": source_url,
            })

        # 4. Embed and Store
        if texts_to_embed:
            # Using org_id as namespace for isolation
            # namespace = f"org_{org_id}"
            # For verification consistency, let's use the same namespace or a 'production' one?
            # verify_ingestion used "test_verification_org_0"
            # Ingest router uses f"org_{org_id}"
            # Let's use f"org_{org_id}" to mimic prod behavior
            namespace = f"org_{org_id}"
            
            print(f"Embedding {len(texts_to_embed)} items into namespace '{namespace}'...")
            vector_service.embed_and_store(texts_to_embed, metadatas, namespace=namespace)
            print("✅ Ingestion Complete!")
            
    except Exception as e:
        print(f"CRITICAL ERROR during ingestion: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    run_ingestion()
