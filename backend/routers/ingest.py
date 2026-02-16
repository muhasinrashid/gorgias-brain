from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from backend.database import get_db
from backend.adapters.context import get_client_context
from backend.services.pii_scrubber import PIIService
from backend.services.vector_store import VectorService
from backend.models import KnowledgeChunk
from backend.dependencies import get_vector_service, verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])

@router.post("/historical")
def ingest_historical_tickets(
    org_id: int, 
    db: Session = Depends(get_db),
    vector_service: VectorService = Depends(get_vector_service)
):
    """
    Batches Gorgias 'Closed' tickets, scrubs them, embeds them, and stores them.
    This is an async-heavy operation, suitable for background tasks (e.g., Celery/Redis Queue).
    For now, we implement it synchronously for the PoC/Phase 1.
    """
    
    # 1. Adapt Context and Fetch
    try:
        adapter = get_client_context(org_id, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Gorgias API doesn't support query-param filtering — fetch all, filter in code
    try:
        # Fetch up to 500 tickets using pagination
        all_tickets = []
        params = {"limit": 100}
        cursor = None
        
        for _ in range(5):  # Max 5 pages = 500 tickets
            if cursor:
                params["cursor"] = cursor
            
            page_data = adapter.client.get("/api/tickets", params=params, headers=adapter._get_headers()).json()
            items = page_data.get("data", [])
            meta = page_data.get("meta", {})
            cursor = meta.get("next_cursor")
            
            all_tickets.extend(items)
            if not cursor or not items:
                break
                
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch tickets from Gorgias: {str(e)}")
    
    # Filter for closed tickets only
    tickets = [t for t in all_tickets if t.get("status") == "closed"]
    
    if not tickets:
        return {"message": "No closed tickets found to ingest."}

    # 2. Initialize Services
    pii_scrubber = PIIService()
    # vector_service injected
    
    texts_to_embed = []
    metadatas = []
    
    # 3. Process Logic — Extract High-Quality Question-Resolution Pairs
    for ticket in tickets:
        ticket_id = ticket.get("id")
        subject = ticket.get("subject", "")
        
        question_text = ""
        resolution_text = ""
        
        # Fetch full ticket with messages from Gorgias API
        if hasattr(adapter, 'fetch_ticket'):
            full_ticket = adapter.fetch_ticket(str(ticket_id))
            if full_ticket:
                raw_messages = full_ticket.get("messages", [])
                if isinstance(raw_messages, dict):
                    messages = raw_messages.get("data", [])
                elif isinstance(raw_messages, list):
                    messages = raw_messages
                else:
                    messages = []
                
                # Sort messages by creation date if available, or assume chronological
                # We need:
                # 1. The FIRST customer message (The Question)
                # 2. The LAST internal/agent message (The Resolution)
                
                customer_messages = [m for m in messages if (m.get("sender", {}).get("type") == "customer" or m.get("from_agent") is False)]
                agent_messages = [m for m in messages if (m.get("sender", {}).get("type") == "internal" or m.get("from_agent") is True)]
                
                if customer_messages:
                    # Get first message body
                    m = customer_messages[0]
                    question_text = m.get("body_text", "") or m.get("stripped_text", "") or ""
                
                if agent_messages:
                    # Get last message body (often the one that solved it)
                    # Filter out short "Thank you" or "Closing ticket" messages if possible
                    for m in reversed(agent_messages):
                        body = m.get("body_text", "") or m.get("stripped_text", "") or ""
                        if len(body.strip()) > 30: # Heuristic: resolutions are usually > 30 chars
                            resolution_text = body.strip()
                            break
                    
                    if not resolution_text and agent_messages:
                         resolution_text = agent_messages[-1].get("body_text", "") or agent_messages[-1].get("stripped_text", "") or ""

        # Build the structured Knowledge Chunk
        # If we couldn't pair, fall back to excerpt/subject
        if not question_text:
             question_text = ticket.get("excerpt") or ticket.get("subject") or "No content"
             
        final_doc_text = f"### QUESTION: {subject}\n{question_text.strip()}\n\n"
        
        if resolution_text:
            final_doc_text += f"### RESOLUTION:\n{resolution_text.strip()}"
        else:
            # If no resolution found, maybe it was a simple outbound or closed without reply
            # Use whole logic as fallback
            final_doc_text += f"### CONTEXT: (Ticket Closed)"

        # Scrub PII
        scrubbed_text = pii_scrubber.scrub(final_doc_text)
        
        if not scrubbed_text.strip():
            continue

        # Prepare for Vector Store
        texts_to_embed.append(scrubbed_text)
        
        # Metadata logic
        domain = adapter.base_url.replace("https://", "").split(".")[0]
        source_url = f"https://{domain}.gorgias.com/app/ticket/{ticket_id}"

        metadatas.append({
            "org_id": org_id,
            "source_id": str(ticket_id),
            "source_type": "gorgias_ticket",
            "source_url": source_url,
            "subject": subject
        })

    # 4. Embed and Store
    if texts_to_embed:
        namespace = f"org_{org_id}"
        vector_service.embed_and_store(texts_to_embed, metadatas, namespace=namespace)
        
        return {"message": f"Successfully ingested {len(texts_to_embed)} tickets with full message content."}
    
    return {"message": "No valid text content found to ingest."}

@router.post("/web")
def ingest_web_page(
    url: str, 
    org_id: int, 
    db: Session = Depends(get_db)
):
    """
    Ingests a single web page (FAQ, Policy) into the knowledge base.
    """
    from backend.services.crawler import CrawlerService
    
    # CrawlerService instantiation might be heavy if it uses browsers, 
    # but regular requests are fine. If heavy, move to dependencies.
    crawler = CrawlerService()
    result = crawler.crawl_and_ingest(url, org_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result
