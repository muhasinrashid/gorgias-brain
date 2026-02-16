import httpx
from .base import BaseAdapter
from typing import Any, Dict, Optional, List
import base64

class GorgiasAdapter(BaseAdapter):
    def __init__(self, api_key: str, base_url: str, username: str):
        super().__init__(api_key, base_url)
        self.username = username
        self.client = httpx.Client(base_url=base_url)

    def _get_headers(self):
        auth_str = f"{self.username}:{self.api_key}"
        auth_bytes = auth_str.encode('ascii')
        base64_bytes = base64.b64encode(auth_bytes)
        base64_auth = base64_bytes.decode('ascii')
        
        return {
            "Authorization": f"Basic {base64_auth}",
            "Content-Type": "application/json"
        }

    def health_check(self) -> bool:
        try:
            response = self.client.get("/api/users/me", headers=self._get_headers())
            return response.status_code == 200
        except Exception:
            return False

    def fetch_tickets(self, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        response = self.client.get("/api/tickets", params=params, headers=self._get_headers())
        response.raise_for_status()
        return response.json().get("data", [])

    def fetch_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        try:
            response = self.client.get(f"/api/tickets/{ticket_id}", headers=self._get_headers())
            return response.json() if response.status_code == 200 else None
        except Exception:
            return None

    def fetch_orders(self, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        # Gorgias might have order integrations but primarily tickets
        # Should we fetch external orders linked to tickets? Or return empty if not applicable?
        # Assuming we just fetch Tickets for Gorgias primarily.
        return []

    def fetch_products(self, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        # Not applicable for Gorgias usually unless using their internal product catalog if it exists
        return []

    def get_order_status(self, email: str) -> List[Dict[str, Any]]:
        # Gorgias is not an E-commerce platform, return empty
        return []
