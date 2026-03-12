import json
import asyncio
from typing import List, Dict, Any, Optional
from langchain_openai import ChatOpenAI, AzureChatOpenAI
import os
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from backend.services.vector_store import VectorService
from backend.adapters.bigcommerce import BigCommerceAdapter
from pydantic import BaseModel, Field

class ReasoningOutput(BaseModel):
    suggested_draft: str = Field(description="The suggested response draft.")
    confidence_score: float = Field(description="Confidence score between 0 and 1.")
    source_references: List[str] = Field(description="List of source URLs or IDs used.", default=[])

class ReasoningEngine:
    def __init__(self, vector_service: VectorService):
        self.vector_service = vector_service
        if os.getenv("AZURE_OPENAI_API_KEY"):
            self.llm = AzureChatOpenAI(
                azure_deployment=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "gpt-4o-mini"),
                openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                temperature=0
            )
        else:
            self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.parser = JsonOutputParser(pydantic_object=ReasoningOutput)

    def _get_system_prompt(self, max_score: float, has_conversation_history: bool = False) -> str:
        prompt = """You are a professional Customer Support AI assistant.

Your Goal: Generate specific, accurate, and helpful support response drafts.

Core Rules:
1. ONLY use the provided context (Retrieved Context, Order Status, Conversation History) to answer.
2. NEVER invent policies, product details, or information not present in the context.
3. Use a warm, professional, empathetic tone.
4. Do NOT include placeholder tokens like [Customer's Name], [Your Name], or [Company Name] — either use the real name if available, or omit it.
5. Keep responses concise and directly answer the customer's question.
"""
        if has_conversation_history:
            prompt += """
Conversation Awareness:
- You are given the FULL conversation history below. READ IT CAREFULLY.
- The customer's latest message is a FOLLOW-UP. Understand what was previously discussed.
- Do NOT repeat information or questions already covered in earlier messages.
- If the customer answers a question you previously asked (e.g., specifying a product model), use that answer to provide the specific information they need.
- Connect the dots between the latest message and the conversation context.
"""

        prompt += """
Input Context:
- Retrieved Context: Similar past tickets and knowledge base articles.
- Customer Order Status: Real-time data (if available).
"""

        if max_score < 0.35:
            prompt += """
Hallucination Control:
- The similarity score of the best knowledge match is LOW (< 0.35).
- You MUST start your 'suggested_draft' with: "I found some related information, but I'd recommend verifying with our team:"
- Set confidence_score below 0.35.
"""
        else:
            prompt += """
Hallucination Control:
- You have good knowledge context. Use it to draft a clear, specific response.
"""

        prompt += """
Response Format:
- Return ONLY valid JSON with keys: suggested_draft, confidence_score (0.0-1.0), and source_references (list of strings).
- The suggested_draft should be a ready-to-send email response.
"""
        return prompt

    async def generate_response(
        self, 
        current_ticket_body: str, 
        customer_email: str, 
        org_id: int, 
        bigcommerce_adapter: BigCommerceAdapter,
        search_results: List[Any] = None,
        conversation_history: str = None,
        search_query: str = None
    ) -> Dict[str, Any]:
        
        # Step A: Query Pinecone (if search_results not provided)
        # Use enriched search_query if provided, otherwise fall back to ticket body
        effective_query = search_query or current_ticket_body
        
        if search_results is None:
            # We assume org_id is used as namespace
            namespace = f"org_{org_id}"
            
            # Using asyncio.to_thread to run sync calls in a separate thread
            search_task = asyncio.to_thread(
                self.vector_service.similarity_search_with_score,
                query=effective_query, 
                k=10, 
                namespace=namespace
            )
        else:
            # Wrap pre-fetched results in a completed future
            search_task = asyncio.Future()
            search_task.set_result(search_results)

        orders_task = asyncio.to_thread(
            bigcommerce_adapter.get_order_status,
            email=customer_email
        )

        results = await asyncio.gather(search_task, orders_task)
        search_results, order_status = results
        
        # Process Search Results and Apply Recency Weighting
        import time
        current_time = int(time.time())
        day_seconds = 86400
        ninety_days = 90 * day_seconds
        
        max_score = 0.0
        context_texts = []
        source_refs = []

        refined_results = []
        if search_results:
             for doc, score in search_results:
                 doc_timestamp = doc.metadata.get('unix_timestamp', 0)
                 age = current_time - doc_timestamp
                 boost = 1.0
                 if age < ninety_days:
                     boost = 1.1 # 10% boost for recency
                 
                 refined_results.append((doc, score, score * boost))
             
             # Sort by boosted score
             refined_results.sort(key=lambda x: x[2], reverse=True)
             
             # Slice top 3
             top_3 = refined_results[:3]
             
             # Extract Context and Max Raw Score
             for doc, raw_score, boosted_score in top_3:
                 if raw_score > max_score:
                     max_score = raw_score
                 
                 # Include Ticket ID in the context so LLM can cite it
                 ticket_id = doc.metadata.get('source_id', 'Unknown')
                 context_texts.append(f"Ticket #{ticket_id}: {doc.page_content}")
                 
                 # Add formatted reference
                 if 'source_url' in doc.metadata and ticket_id != 'Unknown':
                     source_refs.append(f"Ticket #{ticket_id}")
                 elif 'source_url' in doc.metadata:
                     source_refs.append(doc.metadata['source_url'])
        
        # Step C: LLM Construction
        has_history = bool(conversation_history)
        
        # Build the user message with optional conversation history
        user_message = ""
        
        if conversation_history:
            user_message += f"""Conversation History (oldest to newest):
{conversation_history}

"""
        
        user_message += f"""Latest Customer Message: {current_ticket_body}

Top Max Similarity Score: {max_score}

Retrieved Context:
{json.dumps(context_texts, indent=2)}

Real-time Order Status:
{json.dumps(order_status, indent=2)}
"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", self._get_system_prompt(max_score, has_conversation_history=has_history)),
            ("user", user_message)
        ])
        
        chain = prompt | self.llm | self.parser
        
        try:
            # invoke is usually sync, so we should use ainvoke for async
            response = await chain.ainvoke({})
            
            # Ensure source_references are populated if empty in response but present in context
            if not response.get("source_references") and source_refs:
                 response["source_references"] = list(set(source_refs))
                 
            return response
        except Exception as e:
            return {
                "suggested_draft": f"Error generating response: {str(e)}",
                "confidence_score": 0.0,
                "source_references": []
            }
