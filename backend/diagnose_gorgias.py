
import os
import sys
import httpx
import base64

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)

TOKEN = "cmVuaWwubWF0aGV3c0BuZW9wcmF4aXMuaW46NTI5M2EzM2JhNjU5MjhhZjViMWQ0ZDMzZmRmZWFkZDhlMzY2ODQyYjBkM2UwZjJiNzcxNTg0MTBkMDYzMGRlZg=="
HEADERS = {
    "Authorization": f"Basic {TOKEN}",
    "Content-Type": "application/json"
}

DOMAINS = [
    "https://formexwatches.gorgias.com",
    "https://formexwatch.gorgias.com",
    "https://gauger.gorgias.com"
]

ENDPOINTS = [
    "/api/users/me",
    "/api/tickets?limit=1"
]

print("--- Starting Diagnostics ---")
print(f"Token Length: {len(TOKEN)}")

# Decode token to verify contents (safely print partial)
try:
    decoded = base64.b64decode(TOKEN).decode('utf-8')
    parts = decoded.split(':')
    if len(parts) == 2:
        print(f"Decodes to: User='{parts[0]}', Key='...{parts[1][-4:]}'")
    else:
        print(f"Decodes to something unexpected: {decoded[:10]}...")
except Exception as e:
    print(f"Failed to decode token: {e}")

print("\nTesting Domains:")

with httpx.Client(verify=False) as client: # Disable SSL verification temporarily to rule out cert issues
    for domain in DOMAINS:
        print(f"\nChecking Domain: {domain}")
        for endpoint in ENDPOINTS:
            url = f"{domain}{endpoint}"
            try:
                print(f"  GET {url}")
                resp = client.get(url, headers=HEADERS, timeout=10.0)
                print(f"    Status: {resp.status_code}")
                # Print partial response
                print(f"    Body: {resp.text[:200]}")
                
                if resp.status_code == 200:
                    print(f"    ✅ SUCCESS!")
            except httpx.RequestError as exc:
                print(f"    ❌ Request Error: {exc}")
            except Exception as exc:
                print(f"    ❌ Exception: {exc}")

print("\n--- Diagnostics Complete ---")
