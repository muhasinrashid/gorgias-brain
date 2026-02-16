from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from backend.database import get_db
from backend.adapters.context import get_client_context
from backend.services.reasoning_engine import ReasoningEngine
from backend.dependencies import get_reasoning_engine, verify_api_key

router = APIRouter()

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


@router.post("/gorgias-widget", dependencies=[Depends(verify_api_key)])
@router.get("/gorgias-widget", dependencies=[Depends(verify_api_key)])
async def gorgias_widget(
    ticket_id: str = None,
    subject: str = None,
    customer_email: str = None,
    org_id: int = 1,
    request_body: Dict[str, Any] = Body(default=None),
    db: Session = Depends(get_db),
    engine: ReasoningEngine = Depends(get_reasoning_engine)
) -> Dict[str, Any]:
    """
    Gorgias HTTP Integration endpoint.
    Accepts ticket data via URL query params (using Gorgias template variables):
      ?ticket_id={{ticket.id}}&subject={{ticket.subject}}&customer_email={{ticket.customer.email}}
    """
    try:
        adapter = get_client_context(org_id, db)
        
        # Priority 1: Use URL query params (from Gorgias template variables)
        ticket_body = subject or ""
        email = customer_email or ""
        
        # Priority 2: Try POST body if available
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
        
        # Priority 3: Fetch from Gorgias API (formexwatch) as last resort
        if not ticket_body and ticket_id and hasattr(adapter, 'fetch_ticket'):
            ticket_data = adapter.fetch_ticket(ticket_id)
            if ticket_data:
                ticket_body = (
                    ticket_data.get("excerpt") or 
                    ticket_data.get("subject") or ""
                )
                customer = ticket_data.get("customer", {})
                email = customer.get("email", "") if isinstance(customer, dict) else ""
        
        if not ticket_body:
            return {
                "type": "text",
                "text": "⚠️ No ticket data received. Make sure the URL includes: &subject={{ticket.subject}}"
            }

        # 1. Perform Vector Search first (Fast)
        import asyncio
        namespace = f"org_{org_id}"
        search_results = await asyncio.to_thread(
            engine.vector_service.similarity_search_with_score,
            query=ticket_body,
            k=5,
            namespace=namespace
        )
        
        if not search_results:
             return {
                "type": "text",
                "text": "🔍 No similar past tickets found."
            }

        # 2. Try to generate AI Answer using the ALREADY fetched results
        try:
            result = await asyncio.wait_for(
                engine.generate_response(
                    current_ticket_body=ticket_body,
                    customer_email=email,
                    org_id=org_id,
                    bigcommerce_adapter=adapter,
                    search_results=search_results # Pass existing results!
                ),
                timeout=3.5  # Time for LLM only (search is already done)
            )
            
            draft = result.get("suggested_draft", "No suggestion available.")
            confidence = result.get("confidence_score", 0)
            sources = result.get("source_references", [])
            
            confidence_emoji = "🟢" if confidence >= 0.6 else "🟡" if confidence >= 0.35 else "🔴"
            
            # Simplified Source Format for Widget
            sources_text = ""
            if sources:
                 # Extract ticket IDs if possible
                 sources_text = "\n\n**Refs:** " + ", ".join(s.replace("Ticket #", "#") for s in sources[:3])
            
            return {
                "type": "text",
                "text": f"**{confidence_emoji} Smart Assist** ({confidence:.0%})\n\n{draft}{sources_text}"
            }

        except asyncio.TimeoutError:
            # 3. Fallback: Use the SAME search_results we already have (Instant)
            matches = []
            valid_count = 0
            
            for doc, score in search_results:
                content = doc.page_content.strip()
                
                # Filter low quality content 
                if "(No description provided)" in content or len(content) < 50:
                    continue

                if "Subject:" in content:
                    content = content.replace("Subject:", "**Subject:**")
                if "Excerpt:" in content:
                    content = content.replace("Excerpt:", "\n**Excerpt:**")
                
                if len(content) > 300:
                    content = content[:300] + "..."
                    
                tid = doc.metadata.get('source_id', '?')
                matches.append(f"🎫 **#{tid}** ({score:.0%})\n{content}")
                valid_count += 1
                if valid_count >= 3:
                    break
            
            matches_text = "\n\n---\n\n".join(matches)
            
            if not matches:
                 return {"type": "text", "text": "🔍 Found matches but they lacked content."}

            return {
                 "type": "text",
                 "text": f"**🟡 Smart Assist (Search Results)**\n\n{matches_text}"
            }
            
    except Exception as e:
        print(f"Error in gorgias_widget: {e}")
        return {
            "type": "text",
            "text": f"⚠️ Error: {str(e)}"
        }
