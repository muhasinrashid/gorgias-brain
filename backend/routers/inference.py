from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
import time
import asyncio
import re

from backend.database import get_db
from backend.adapters.context import get_client_context
from backend.services.reasoning_engine import ReasoningEngine
from backend.dependencies import get_reasoning_engine, verify_api_key

router = APIRouter()


def _strip_html(html: str) -> str:
    """Strip HTML tags to get plain text."""
    if not html:
        return ""
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _extract_message_text(msg: dict) -> str:
    """Extract the best available text from a Gorgias message."""
    body_text = (msg.get("body_text") or "").strip()
    if body_text:
        return body_text
    stripped_text = (msg.get("stripped_text") or "").strip()
    if stripped_text:
        return stripped_text
    return _strip_html(msg.get("body_html") or "")


async def _build_conversation_context(
    adapter, ticket_id: str, timeout: float = 1.0
) -> tuple:
    """Fetch all messages for a ticket and build a chronological conversation string.
    
    Returns a tuple of:
        (conversation_string, latest_customer_message)
    
    conversation_string is formatted like:
        [Customer]: What is the return policy?
        [Agent]: Our return policy is 30 days...
        [Customer]: I want to know for Reef Watches
    
    latest_customer_message is the text of the most recent customer message.
    
    Returns ("", "") if fetch fails or times out.
    """
    try:
        def _sync_fetch():
            msg_resp = adapter.client.get(
                f"/api/tickets/{ticket_id}/messages",
                headers=adapter._get_headers()
            )
            if msg_resp.status_code != 200:
                return []
            msg_data = msg_resp.json()
            if isinstance(msg_data, dict):
                return msg_data.get("data", [])
            elif isinstance(msg_data, list):
                return msg_data
            return []
        
        messages = await asyncio.wait_for(
            asyncio.to_thread(_sync_fetch),
            timeout=timeout
        )
    except Exception as e:
        print(f"⏱️ Could not fetch conversation history: {e}")
        return "", ""
    
    if not messages or len(messages) <= 1:
        return "", ""  # No history to add (single message = no follow-up context needed)
    
    # Sort messages chronologically (oldest first)
    messages.sort(key=lambda m: m.get("created_datetime", ""))
    
    # Build conversation string
    conversation_parts = []
    for msg in messages:
        text = _extract_message_text(msg)
        if not text or len(text.strip()) < 5:
            continue
        
        # Determine sender
        from_agent = msg.get("from_agent")
        if from_agent is True:
            sender = "Agent"
        elif from_agent is False:
            sender = "Customer"
        else:
            sender_type = (msg.get("sender") or {}).get("type", "")
            if sender_type in ("customer", "user"):
                sender = "Customer"
            elif sender_type in ("internal", "agent", "collaborator"):
                sender = "Agent"
            else:
                sender = "Unknown"
        
        # Truncate very long messages to avoid blowing up the prompt
        if len(text) > 500:
            text = text[:500] + "..."
        
        conversation_parts.append(f"[{sender}]: {text}")
    
    # Extract the latest customer message for search query enrichment
    latest_customer_msg = ""
    for msg in reversed(messages):
        from_agent = msg.get("from_agent")
        is_customer = (from_agent is False) or (
            (msg.get("sender") or {}).get("type", "") in ("customer", "user")
        )
        if is_customer:
            text = _extract_message_text(msg)
            if text and len(text.strip()) >= 5:
                latest_customer_msg = text.strip()
                break
    
    return "\n".join(conversation_parts), latest_customer_msg


def _build_search_query(subject: str, latest_message: str) -> str:
    """Combine ticket subject with latest message for a richer vector search query.
    
    For follow-ups like 'I want to know for Reef Watches', combining with
    the subject 'Formex Watch Recommendation' gives vector search much better context.
    """
    parts = []
    if subject and subject.strip():
        parts.append(subject.strip())
    if latest_message and latest_message.strip():
        parts.append(latest_message.strip())
    return " | ".join(parts) if parts else latest_message or ""


class InferenceRequest(BaseModel):
    ticket_id: str
    ticket_body: Optional[str] = None
    customer_email: Optional[str] = None
    org_id: int

@router.post("/suggest", dependencies=[Depends(verify_api_key)])
async def generate_suggestion(
    request: InferenceRequest, 
    db: Session = Depends(get_db),
    engine: ReasoningEngine = Depends(get_reasoning_engine)
) -> Dict[str, Any]:
    """
    Generates a support response suggestion.
    """
    try:
        # 1. Get Adapter
        adapter = get_client_context(request.org_id, db)

        # Hydrate if missing
        ticket_body = request.ticket_body
        customer_email = request.customer_email

        if (not ticket_body or not customer_email) and hasattr(adapter, 'fetch_ticket'):
            ticket_data = adapter.fetch_ticket(request.ticket_id)
            if ticket_data:
                if not ticket_body:
                     # Gorgias uses 'excerpt' for body, also check messages and subject
                     ticket_body = (
                         ticket_data.get("excerpt") or 
                         ticket_data.get("description") or 
                         ticket_data.get("subject") or 
                         ""
                     )
                     # If messages exist, use the first customer message body
                     raw_messages = ticket_data.get("messages", [])
                     # Handle both list format and {"data": [...]} format
                     if isinstance(raw_messages, dict):
                         messages = raw_messages.get("data", [])
                     elif isinstance(raw_messages, list):
                         messages = raw_messages
                     else:
                         messages = []
                     if messages and not ticket_body:
                         ticket_body = messages[0].get("body_text", "") or messages[0].get("body_html", "")
                if not customer_email:
                     customer = ticket_data.get("customer", {})
                     customer_email = customer.get("email") if isinstance(customer, dict) else str(customer)
        
        if not ticket_body:
            raise HTTPException(status_code=400, detail="Ticket body is required and could not be fetched.")
        if not customer_email:
             customer_email = ""

        # 2. Generate Response using injected Engine
        result = await engine.generate_response(
            current_ticket_body=ticket_body,
            customer_email=customer_email,
            org_id=request.org_id,
            bigcommerce_adapter=adapter
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        # Log the full error in production logging system
        print(f"Error in generate_suggestion: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error during suggestion generation.")
async def handle_ticket(
    ticket_id: str,
    subject: str,
    customer_email: str,
    org_id: int,
    request_body: Dict[str, Any],
    adapter,
    engine
):
    print(f"🚀 Starting background processing for ticket {ticket_id}")
    try:
        ticket_body = subject or ""
        email = customer_email or ""
        
        # 1. Resolve inputs
        if not ticket_body and request_body:
            ticket_data = request_body.get("ticket", {})
            message_data = request_body.get("message", {})
            ticket_body = (
                message_data.get("body_text", "") or
                ticket_data.get("excerpt", "") or
                ticket_data.get("subject", "") or ""
            )
            customer = ticket_data.get("customer", {})
            if isinstance(customer, dict) and not email:
                email = customer.get("email", "")
        
        if not ticket_body and ticket_id and hasattr(adapter, 'client'):
            try:
                ticket_data = adapter.fetch_ticket(ticket_id)
                if ticket_data:
                    ticket_body = ticket_data.get("excerpt") or ticket_data.get("subject") or ""
                    customer = ticket_data.get("customer", {})
                    email = customer.get("email", "") if isinstance(customer, dict) else ""
            except Exception as e:
                print(f"⏱️ API fetch failed: {e}")

        if not ticket_body:
            print(f"⚠️ No ticket body found, aborting background task for {ticket_id}")
            return

        # 2. Fetch Conversation
        conversation_history = ""
        latest_customer_msg = ""
        ticket_subject = subject or ""

        if ticket_id and hasattr(adapter, 'client'):
            try:
                # We are in background, so we have 30s. No problem.
                conversation_history, latest_customer_msg = await _build_conversation_context(
                    adapter, ticket_id, timeout=10.0
                )
                if conversation_history:
                    print(f"📝 Conversation history ({len(conversation_history)} chars)")
            except Exception as e:
                print(f"⏱️ Conversation fetch failed: {e}")

        if latest_customer_msg and (ticket_body == ticket_subject or not ticket_body):
            ticket_body = latest_customer_msg
            print(f"📌 Using latest customer message as ticket_body")
            
        search_query = _build_search_query(ticket_subject, ticket_body)

        # 3. Vector search
        namespace = f"org_{org_id}"
        try:
            search_results = await asyncio.to_thread(
                engine.vector_service.similarity_search_with_score,
                query=search_query, k=5, namespace=namespace
            )
        except Exception as e:
            print(f"⚠️ Vector search failed: {e}")
            search_results = []
            
        if not search_results:
            print(f"⚠️ No search results, aborting.")
            if ticket_id and hasattr(adapter, 'add_internal_note'):
                adapter.add_internal_note(ticket_id, "🔍 Smart Assist: No relevant knowledge found.")
            return

        # 4. LLM Generation
        try:
            result = await engine.generate_response(
                current_ticket_body=ticket_body,
                customer_email=email,
                org_id=org_id,
                bigcommerce_adapter=adapter,
                search_results=search_results,
                conversation_history=conversation_history,
                search_query=search_query
            )
        except Exception as e:
            print(f"⚠️ LLM failed: {e}")
            return

        # 5. Post Internal Note
        suggested_draft = result.get("suggested_draft", "")
        confidence = result.get("confidence_score", 0.0)
        sources = result.get("source_references", [])
        
        confidence_emoji = "🟢" if confidence >= 0.8 else "🟡" if confidence >= 0.35 else "🔴"
        
        sources_text = ""
        if sources:
            source_links = []
            for src in sources:
                if src.startswith("http"):
                    source_links.append(f"[{src.split('/')[-1]}]({src})")
                else:
                    source_links.append(f"#{src}")
            sources_text = f"\n\n**Refs:** {', '.join(source_links)}"
        
        final_text = f"{confidence_emoji} **Smart Assist AI** ({confidence:.0%})\n\n{suggested_draft}{sources_text}"

        if ticket_id and hasattr(adapter, 'add_internal_note'):
            note_response = adapter.add_internal_note(ticket_id, final_text)
            if note_response:
                print(f"✅ Posted internal note to ticket {ticket_id}", flush=True)
            else:
                print(f"⚠️ Failed to post internal note to ticket {ticket_id}. Check API credentials and ticket ID.", flush=True)

    except Exception as e:
        import traceback
        traceback.print_exc()
        if ticket_id and hasattr(adapter, 'add_internal_note'):
            adapter.add_internal_note(ticket_id, f"⚠️ Error analyzing ticket: {str(e)}")


@router.post("/gorgias-widget", dependencies=[Depends(verify_api_key)])
@router.get("/gorgias-widget", dependencies=[Depends(verify_api_key)])
async def gorgias_widget(
    background_tasks: BackgroundTasks,
    ticket_id: str = None,
    subject: str = None,
    customer_email: str = None,
    org_id: int = 1,
    request_body: Dict[str, Any] = Body(default=None),
    db: Session = Depends(get_db),
    engine: ReasoningEngine = Depends(get_reasoning_engine)
) -> Dict[str, Any]:
    try:
        adapter = get_client_context(org_id, db)
        
        if ticket_id:
            background_tasks.add_task(
                handle_ticket, 
                ticket_id=ticket_id, 
                subject=subject, 
                customer_email=customer_email, 
                org_id=org_id, 
                request_body=request_body, 
                adapter=adapter, 
                engine=engine
            )
            return {
                "type": "text", 
                "text": "⏳ Smart Assist is analyzing your ticket... (Check internal notes shortly)"
            }
        else:
            return {
                "type": "text",
                "text": "⚠️ No ticket_id provided."
            }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"type": "text", "text": f"⚠️ Error: {str(e)}"}
