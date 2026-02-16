from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
import time
import asyncio

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
    # --- TOTAL TIME BUDGET: 4.5 Seconds (Gorgias kills at 5.0s) ---
    start_time = time.time()
    TOTAL_BUDGET = 4.5
    search_results = []
    ticket_body = subject or ""
    email = customer_email or ""
    
    try:
        adapter = get_client_context(org_id, db)
        
        # 1. Resolve inputs (Fetch from Gorgias if needed)
        # Wrap this in a small timeout too if possible, but for now we'll just track it
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
        
        if not ticket_body and ticket_id and hasattr(adapter, 'fetch_ticket'):
            # Fetching from API can be slow
            try:
                ticket_data = await asyncio.wait_for(
                    asyncio.to_thread(adapter.fetch_ticket, ticket_id),
                    timeout=1.5 # Max 1.5s for ticket fetch
                )
                if ticket_data:
                    ticket_body = ticket_data.get("excerpt") or ticket_data.get("subject") or ""
                    customer = ticket_data.get("customer", {})
                    email = customer.get("email", "") if isinstance(customer, dict) else ""
            except asyncio.TimeoutError:
                print(f"⏱️ Gorgias API fetch timed out for ticket {ticket_id}")

        if not ticket_body:
            return {
                "type": "text",
                "text": "⚠️ No ticket data received. Make sure the URL includes: &subject={{ticket.subject}}"
            }

        # 2. Main Processing Block (Search + AI)
        try:
            # Calculate remaining time for the core logic
            remaining_for_core = TOTAL_BUDGET - (time.time() - start_time)
            if remaining_for_core <= 1.0:
                 raise asyncio.TimeoutError("Not enough time left for AI/Search")

            # Perform Search & AI together in the remaining time
            async def run_pipeline():
                # Perform Search
                namespace = f"org_{org_id}"
                results = await asyncio.to_thread(
                    engine.vector_service.similarity_search_with_score,
                    query=ticket_body,
                    k=5,
                    namespace=namespace
                )
                
                # Check time before LLM
                if time.time() - start_time > 3.0: # If search took too long
                     return {"search_results": results, "llm_skipped": True}

                # Generate AI Response
                result = await engine.generate_response(
                    current_ticket_body=ticket_body,
                    customer_email=email,
                    org_id=org_id,
                    bigcommerce_adapter=adapter,
                    search_results=results
                )
                return {"llm_result": result, "search_results": results}

            pipeline_result = await asyncio.wait_for(run_pipeline(), timeout=remaining_for_core)
            search_results = pipeline_result["search_results"]
            
            if "llm_result" in pipeline_result:
                result = pipeline_result["llm_result"]
                suggested_draft = result["suggested_draft"]
                confidence = result.get("confidence_score", 0.0)
                sources = result.get("source_references", [])
                
                sources_text = ""
                if sources:
                     sources_text = "\n\n**Refs:** " + ", ".join(s.replace("Ticket #", "#") for s in sources[:3])
                
                confidence_emoji = "🟢" if confidence >= 0.6 else "🟡" if confidence >= 0.35 else "🔴"
                
                return {
                    "type": "text",
                    "text": f"**{confidence_emoji} Smart Assist** ({confidence:.0%})\n\n{suggested_draft}{sources_text}"
                }
            else:
                # LLM was skipped but we have search results
                raise asyncio.TimeoutError()

        except asyncio.TimeoutError:
            # 3. Fallback: Return raw search results (Instant)
            print("⏱️ Timeout reached! Returning search results.")
            if not search_results:
                 return {"type": "text", "text": "🔍 Search results not ready or not found."}

            matches = []
            valid_count = 0
            for doc, score in search_results:
                content = doc.page_content.strip()
                if "(No description provided)" in content or len(content) < 50:
                    continue
                tid = doc.metadata.get('source_id', '?')
                matches.append(f"🎫 **#{tid}** ({score:.0%})\n{content[:200]}...")
                valid_count += 1
                if valid_count >= 3: break
            
            return {
                "type": "text",
                "text": f"**🟡 Smart Assist (Search Results)**\n\n" + "\n\n---\n\n".join(matches)
            }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"type": "text", "text": f"⚠️ Error: {str(e)}"}

