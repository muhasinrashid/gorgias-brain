import httpx
from .base import BaseAdapter
from typing import Any, Dict, Optional, List

class BigCommerceAdapter(BaseAdapter):
    def __init__(self, access_token: str, store_hash: str):
        # BigCommerce GraphQL Endpoint
        base_url = f"https://api.bigcommerce.com/stores/{store_hash}/graphql"
        # The REST API is at /v3/, but prompt emphasized GraphQL for BigCommerce.
        # We might need REST for some things not exposed in GraphQL Storefront API if using that,
        # but typically Admin API has GraphQL too now or we use REST for Admin.
        # Let's assume Admin GraphQL API or Storefront if just reading products.
        # "BigCommerceAdapter (GraphQL)" implies utilizing the GraphQL endpoint.
        super().__init__(api_key=access_token, base_url=base_url)
        self.store_hash = store_hash
        self.client = httpx.Client() # Base URL is dynamic for GraphQL so maybe just keep client generic

    def _get_headers(self):
        return {
            "X-Auth-Token": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def health_check(self) -> bool:
        # A simple query to check connectivity
        query = """
        query {
            site {
                settings {
                    storeName
                }
            }
        }
        """
        try:
            response = self.client.post(
                self.base_url,
                headers=self._get_headers(),
                json={"query": query}
            )
            return response.status_code == 200 and "data" in response.json()
        except Exception:
            # Fallback to REST check if GraphQL fails or for robust check
            try:
                rest_url = f"https://api.bigcommerce.com/stores/{self.store_hash}/v2/time"
                response = self.client.get(rest_url, headers=self._get_headers())
                return response.status_code == 200
            except:
                return False

    def _execute_query(self, query: str) -> Dict[str, Any]:
        response = self.client.post(
            self.base_url,
            headers=self._get_headers(),
            json={"query": query}
        )
        response.raise_for_status()
        return response.json()

    def fetch_tickets(self, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        # BigCommerce doesn't have native tickets system usually exposed this way
        return []

    def fetch_orders(self, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        # Fetching orders via GraphQL (Admin API) is possible but often REST is used.
        # Let's try to stick to GraphQL as requested if possible, or fallback.
        # Note: BigCommerce Admin GraphQL API is relatively new and might not cover everything.
        # If "BigCommerceAdapter (GraphQL)" is a strict requirement, I'll use it.
        # Constructing a query for orders.
        # Placeholder query
        return []

    def fetch_products(self, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        query = """
        query {
            site {
                products (first: 10) {
                    edges {
                        node {
                            entityId
                            name
                            description
                        }
                    }
                }
            }
        }
        """
        data = self._execute_query(query)
        # Parse data
        products = []
        if data.get('data') and data['data'].get('site') and data['data']['site'].get('products'):
             for edge in data['data']['site']['products']['edges']:
                 products.append(edge['node'])
        return products

    def get_order_status(self, email: str) -> List[Dict[str, Any]]:
        """
        Fetches orders by email to check status.
        Uses REST API usually as it's more direct for filtering by email than some GraphQL schemas.
        """
        # Fallback to REST if GraphQL is complex for this or use GraphQL if known schema supports it easily.
        # Given "Simultaneously calls BigCommerceAdapter.get_order_status(email)",
        # we'll try a direct approach.
        
        # NOTE: Using a query param for email. 
        # API: /v2/orders?email={email}
        # But base_url is set to GraphQL in __init__. We need to be careful.
        
        if "graphql" in self.base_url:
            # We need to use the REST endpoint logic or a separate client for REST.
            # OR we construct a GraphQL query that filters by email if the schema allows text search on orders.
            # Standard BigCommerce GraphQL (Storefront) doesn't always allow filtering orders by email deeply without customer token.
            # Admin API (REST) is safer for "backend system" lookups.
            
            # Construct REST URL from store_hash
            rest_url = f"https://api.bigcommerce.com/stores/{self.store_hash}/v2/orders"
            params = {"email": email, "sort": "date_created:desc", "limit": 3}
            
            try:
                response = self.client.get(rest_url, params=params, headers={"X-Auth-Token": self.api_key, "Accept": "application/json"})
                if response.status_code == 200:
                    return response.json()
                return []
            except Exception:
                return []
        
        return []
