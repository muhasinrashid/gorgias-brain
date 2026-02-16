from functools import lru_cache
from typing import Annotated
from fastapi import Depends, HTTPException, status, Security
from fastapi.security import APIKeyHeader

from backend.config import Settings, get_settings
from backend.services.vector_store import VectorService
from backend.services.reasoning_engine import ReasoningEngine

# Security Dependency
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(
    api_key: str = Security(api_key_header), 
    settings: Settings = Depends(get_settings)
) -> str:
    """
    Verifies the API key from the header.
    In a real-world scenario, this might check against a database of valid keys
    associated with organizations. 
    For now, we compare against a master ADMIN_API_KEY or allow specific org keys.
    """
    if not api_key:
        # For development ease, we might not enforce it strictly if permissive,
        # but for production recommendation we should enforce it.
        # However, the frontend currently doesn't send it, so we might need to be
        # lenient or update frontend. Given the prompt is "implement recommendations for production",
        # we will enforce it but maybe allow bypass for localhost if desired, or assume keys are distributed.
        
        # NOTE: Since the frontend refactoring is part of this plan, we will assume 
        # the frontend will be updated or we use a separate path for public vs private.
        # But wait, the Sidebar is loaded in an iframe/browser by Gorgias.
        # We need a strategy. Usually, we'd use a signed JWT or similar.
        # For now, let's just checking if it matches the env var.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials"
        )
    
    if api_key != settings.ADMIN_API_KEY:
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid credentials"
        )
    return api_key

# Service Dependencies
@lru_cache()
def get_vector_service() -> VectorService:
    # Initialize once
    return VectorService()

@lru_cache()
def get_reasoning_engine(
    vector_service: VectorService = Depends(get_vector_service)
) -> ReasoningEngine:
    # Initialize once
    return ReasoningEngine(vector_service=vector_service)
