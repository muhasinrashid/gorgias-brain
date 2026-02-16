from sqlalchemy.orm import Session
from backend.models import Integration
import os
from backend.adapters.gorgias import GorgiasAdapter
from backend.adapters.bigcommerce import BigCommerceAdapter
from backend.adapters.base import BaseAdapter

def get_client_context(org_id: int, db: Session) -> BaseAdapter:
    """
    Instantiates the correct adapter based on the user's active integration.
    """
    try:
        integration = db.query(Integration).filter(
            Integration.org_id == org_id, 
            Integration.is_active == True
        ).first()
    except Exception as e:
        print(f"Warning: Database query failed ({e}). Falling back to environment variables.")
        integration = None

    if not integration:
        # Fallback to environment variables for local development/testing
        # Specifically for Gorgias since user provided .env keys
        if os.getenv("GORGIAS_API_KEY") and os.getenv("GORGIAS_BASE_URL"):
            # Ensure username is present or derived
            username = os.getenv("GORGIAS_USERNAME")
            if not username:
                 # Try to extract from email-like var if exists, or fail
                 pass 
            
            return GorgiasAdapter(
                api_key=os.getenv("GORGIAS_API_KEY"),
                base_url=os.getenv("GORGIAS_BASE_URL"),
                username=username or "default_user" # Provide default if missing to avoid crash
            )
        raise ValueError(f"No active integration found for Org ID {org_id} and no Env vars provided")

    if integration.platform == "gorgias":
        # Check credentials JSON for email/username required for Basic Auth
        # Gorgias uses 'email' as username usually
        email = integration.credentials.get("email")
        if not email:
             raise ValueError("Gorgias integration requires 'email' in credentials.")
        
        return GorgiasAdapter(
            api_key=integration.api_key, 
            base_url=integration.api_url, 
            username=email
        )
    elif integration.platform == "bigcommerce":
        if not integration.store_hash:
             raise ValueError("BigCommerce integration requires 'store_hash'.")
             
        return BigCommerceAdapter(
            access_token=integration.api_key, 
            store_hash=integration.store_hash
        )
    else:
        raise ValueError(f"Unsupported platform: {integration.platform}")
