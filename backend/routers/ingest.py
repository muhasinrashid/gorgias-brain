from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import re

from backend.database import get_db
from backend.adapters.context import get_client_context
from backend.services.pii_scrubber import PIIService
from backend.services.vector_store import VectorService
from backend.models import KnowledgeChunk
from backend.dependencies import get_vector_service, verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])


def _strip_html(html: str) -> str:
    """Strip HTML tags and decode entities to get plain text."""
    if not html:
        return ""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', html)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _extract_message_text(msg: dict) -> str:
    """Extract the best available text from a Gorgias message.
    
    Priority: body_text > stripped_text > stripped HTML from body_html.
    """
    body_text = (msg.get("body_text") or "").strip()
    if body_text:
        return body_text
    
    stripped_text = (msg.get("stripped_text") or "").strip()
    if stripped_text:
        return stripped_text
    
    # Fallback: strip HTML tags from body_html
    body_html = msg.get("body_html") or ""
    return _strip_html(body_html)


@router.post("/historical")
def ingest_historical_tickets(
    org_id: int, 
    limit: int = 50,
    db: Session = Depends(get_db),
    vector_service: VectorService = Depends(get_vector_service)
):
    """
    Batches Gorgias 'Closed' tickets, scrubs them, embeds them, and stores them.
    
    Supports three knowledge extraction modes:
    1. Full Q&A pair: customer question + agent resolution (highest quality)
    2. Agent-only resolution: meaningful agent message without customer question
    3. Subject + content: single-message tickets that still contain knowledge
    
    limit: Max number of tickets to fetch and process (default 50 to avoid timeouts).
    """
    
    # 1. Adapt Context and Fetch
    try:
        adapter = get_client_context(org_id, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Gorgias API doesn't support query-param filtering — fetch all, filter in code
    try:
        # Fetch tickets using pagination
        all_tickets = []
        params = {"limit": 100}  # Gorgias max page size
        cursor = None
        
        # We need to fetch MORE tickets to find enough closed ones with real content
        # Social media mentions, order notifs, etc. are noise — we need real Q&A tickets
        max_pages = (limit // 100) + 3  # Fetch extra pages since many won't qualify
        
        for _ in range(max_pages):
            if cursor:
                params["cursor"] = cursor
            
            page_data = adapter.client.get(
                "/api/tickets", params=params, headers=adapter._get_headers()
            ).json()
            items = page_data.get("data", [])
            meta = page_data.get("meta", {})
            cursor = meta.get("next_cursor")
            
            all_tickets.extend(items)
            
            if len(all_tickets) >= limit * 3 or not cursor or not items:
                break
                
    except Exception as e:
        raise HTTPException(
            status_code=502, 
            detail=f"Failed to fetch tickets from Gorgias: {str(e)}"
        )
    
    # Filter for closed tickets only
    tickets = [t for t in all_tickets if t.get("status") == "closed"]
    
    if not tickets:
        return {"message": "No closed tickets found to ingest."}

    print(f"[ingest] Found {len(tickets)} closed tickets out of {len(all_tickets)} total")

    # 2. Initialize Services
    pii_scrubber = PIIService()
    
    texts_to_embed = []
    metadatas = []
    
    # Counters for debug logging
    stats = {
        "total_closed": len(tickets),
        "qa_pairs": 0,
        "agent_only": 0,
        "subject_content": 0,
        "skipped_no_content": 0,
        "skipped_too_short": 0,
    }
    
    # 3. Process Logic — Extract Knowledge from Tickets
    for ticket in tickets:
        if len(texts_to_embed) >= limit:
            break
            
        ticket_id = ticket.get("id")
        subject = ticket.get("subject", "").strip()
        
        # Fetch messages via the dedicated messages endpoint (more reliable)
        messages = []
        try:
            msg_resp = adapter.client.get(
                f"/api/tickets/{ticket_id}/messages",
                headers=adapter._get_headers()
            )
            if msg_resp.status_code == 200:
                msg_data = msg_resp.json()
                if isinstance(msg_data, dict):
                    messages = msg_data.get("data", [])
                elif isinstance(msg_data, list):
                    messages = msg_data
        except Exception as e:
            print(f"[ingest] Warning: could not fetch messages for ticket {ticket_id}: {e}")
        
        # Fallback: try messages from full ticket if separate endpoint failed
        if not messages and hasattr(adapter, 'fetch_ticket'):
            full_ticket = adapter.fetch_ticket(str(ticket_id))
            if full_ticket:
                raw_messages = full_ticket.get("messages", [])
                if isinstance(raw_messages, dict):
                    messages = raw_messages.get("data", [])
                elif isinstance(raw_messages, list):
                    messages = raw_messages
        
        if not messages:
            stats["skipped_no_content"] += 1
            continue
        
        # Classify messages using `from_agent` (primary) — sender.type is unreliable
        customer_messages = []
        agent_messages = []
        
        for m in messages:
            from_agent = m.get("from_agent")
            if from_agent is True:
                agent_messages.append(m)
            elif from_agent is False:
                customer_messages.append(m)
            else:
                # Unknown sender — try sender.type as fallback
                sender_type = (m.get("sender") or {}).get("type", "")
                if sender_type in ("customer", "user"):
                    customer_messages.append(m)
                elif sender_type in ("internal", "agent", "collaborator"):
                    agent_messages.append(m)
                # else: truly unknown, skip this message
        
        # --- Knowledge Extraction Modes ---
        question_text = ""
        resolution_text = ""
        doc_mode = None
        
        # Mode 1: Full Q&A pair (highest quality)
        if customer_messages and agent_messages:
            # First customer message = The Question
            q_body = _extract_message_text(customer_messages[0])
            if len(q_body) >= 20:  # Relaxed from 50 — short questions are still valid
                question_text = q_body
            
            # Last substantial agent message = The Resolution
            for m in reversed(agent_messages):
                body = _extract_message_text(m)
                if len(body) >= 50:
                    resolution_text = body
                    break
            
            if question_text and resolution_text:
                doc_mode = "qa_pair"
        
        # Mode 2: Agent-only resolution (no customer message, but agent wrote something useful)
        if not doc_mode and agent_messages:
            for m in reversed(agent_messages):
                body = _extract_message_text(m)
                if len(body) >= 50:
                    resolution_text = body
                    doc_mode = "agent_only"
                    break
        
        # Mode 3: Subject + single customer message (still useful as knowledge)
        if not doc_mode and customer_messages and subject:
            body = _extract_message_text(customer_messages[0])
            if len(body) >= 50:
                question_text = body
                doc_mode = "subject_content"
        
        # Build the document based on mode
        if doc_mode == "qa_pair":
            final_doc_text = f"### QUESTION: {subject}\n{question_text}\n\n"
            final_doc_text += f"### RESOLUTION:\n{resolution_text}"
            stats["qa_pairs"] += 1
        elif doc_mode == "agent_only":
            final_doc_text = f"### TOPIC: {subject}\n\n"
            final_doc_text += f"### AGENT RESPONSE:\n{resolution_text}"
            stats["agent_only"] += 1
        elif doc_mode == "subject_content":
            final_doc_text = f"### TOPIC: {subject}\n\n"
            final_doc_text += f"### CONTENT:\n{question_text}"
            stats["subject_content"] += 1
        else:
            stats["skipped_too_short"] += 1
            continue

        # Scrub PII
        scrubbed_text = pii_scrubber.scrub(final_doc_text)
        
        if not scrubbed_text.strip():
            stats["skipped_no_content"] += 1
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
            "subject": subject,
            "extraction_mode": doc_mode,
        })

    print(f"[ingest] Processing stats: {stats}")
    print(f"[ingest] Total documents to embed: {len(texts_to_embed)}")

    # 4. Embed and Store
    if texts_to_embed:
        namespace = f"org_{org_id}"
        vector_service.embed_and_store(texts_to_embed, metadatas, namespace=namespace)
        
        return {
            "message": f"Successfully ingested {len(texts_to_embed)} tickets.",
            "stats": stats
        }
    
    return {
        "message": "No valid text content found to ingest.",
        "stats": stats,
        "hint": "All tickets were too short or lacked meaningful content. Try increasing the limit to find more substantive tickets."
    }

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
    
    crawler = CrawlerService()
    result = crawler.crawl_and_ingest(url, org_id)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


class BatchWebIngestRequest(BaseModel):
    urls: List[str]
    org_id: int


@router.post("/web/batch")
def ingest_web_pages_batch(request: BatchWebIngestRequest):
    """
    Ingests multiple web pages in one pass. Each URL is crawled independently
    via Apify (handles SPA pages with shared canonical URLs).
    
    Example: crawl all FAQ sections at once:
    {
        "urls": [
            "https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Freturns-154421",
            "https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Fshipping-154418",
            "https://formexwatch.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Fpayment-154417"
        ],
        "org_id": 1
    }
    """
    from backend.services.crawler import CrawlerService
    
    if not request.urls:
        raise HTTPException(status_code=400, detail="No URLs provided")
    
    crawler = CrawlerService()
    results = []
    
    for url in request.urls:
        try:
            result = crawler.crawl_and_ingest(url, request.org_id)
            results.append({"url": url, **result})
        except Exception as e:
            results.append({"url": url, "status": "error", "message": str(e)})
    
    succeeded = sum(1 for r in results if r.get("status") == "success")
    total_chunks = sum(r.get("chunks_ingested", 0) for r in results)
    
    return {
        "message": f"Batch complete: {succeeded}/{len(request.urls)} pages ingested, {total_chunks} total chunks.",
        "results": results,
    }
