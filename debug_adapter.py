
import os
import sys
from dotenv import load_dotenv
from backend.adapters.gorgias import GorgiasAdapter

# Load env vars
load_dotenv("backend/.env")

api_key = os.getenv("GORGIAS_API_KEY")
username = os.getenv("GORGIAS_USERNAME")
base_url = os.getenv("GORGIAS_BASE_URL")

print(f"Testing with Base URL: {base_url}")

if not all([api_key, username, base_url]):
    print("Missing environment variables.")
    sys.exit(1)

adapter = GorgiasAdapter(api_key, base_url, username)

# 1. Fetch tickets (any status)
print("Fetching 1 ticket...")
tickets = adapter.fetch_tickets(params={"limit": 1}) # Gorgias uses limit, not per_page usually? API docs say limit/cursor.
# Actually default implementation uses whatever params we pass.
# Let's try to just call it.
print(f"Fetched {len(tickets)} tickets.")

if tickets:
    t = tickets[0]
    tid = str(t["id"])
    print(f"Ticket ID: {tid}")
    print(f"Subject: {t.get('subject')}")
    
    # 2. Fetch specific ticket details using fetch_ticket
    print(f"Fetching details for {tid}...")
    full_ticket = adapter.fetch_ticket(tid)
    
    if full_ticket:
        print("Fetch successful.")
        msgs = full_ticket.get("messages", [])
        if isinstance(msgs, dict):
            msgs = msgs.get("data", [])
        
        print(f"Message count: {len(msgs)}")
        for i, m in enumerate(msgs):
            body = m.get("body_text", "") or m.get("stripped_text", "") or ""
            print(f"Message {i} ({m.get('sender',{}).get('type')}): {body[:100]}...")
    else:
        print("Failed to fetch full ticket.")
else:
    print("No tickets found to test.")
