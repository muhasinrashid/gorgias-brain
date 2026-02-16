from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List

class BaseAdapter(ABC):
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the connection to the external service is healthy."""
        pass

    @abstractmethod
    def fetch_tickets(self, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Fetch support tickets or conversations."""
        pass

    @abstractmethod
    def fetch_orders(self, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Fetch orders."""
        pass

    @abstractmethod
    def fetch_products(self, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Fetch products."""
        pass

    @abstractmethod
    def get_order_status(self, email: str) -> List[Dict[str, Any]]:
        """Fetch order status by email."""
        pass
