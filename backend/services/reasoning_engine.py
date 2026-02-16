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

    def _get_system_prompt(self, max_score: float) -> str:
        prompt = """You are a highly capable Logic Engine for a B2B SaaS Support system.
        
        Your Goal: specific, accurate, and policy-compliant support drafts.
        
        Constraints:
        1. NEVER invent policies. Only use the provided context.
        2. If the context is missing or insufficient, state "UNCERTAIN" as per instructions.
        3. Use a professional, empathetic tone.
        
        Input Context:
        - Past Tickets (Context): Similar issues resolved from the knowledge base.
        - Customer Order Status: Real-time data from BigCommerce.
        
        Hallucination Control:
        """
        if max_score < 0.35:
            prompt += """
            - The similarity score of the best match is LOW (< 0.35).
            - You MUST start your 'suggested_draft' with: "UNCERTAIN: I found related info but check these sources first."
            """
        else:
            prompt += """
            - Use the high confidence context to draft a clear response.
            """
            
        prompt += """
        Return ONLY valid JSON with keys: suggested_draft, confidence_score, and source_references.
        """
        return prompt

    async def generate_response(
        self, 
        current_ticket_body: str, 
        customer_email: str, 
        org_id: int, 
        bigcommerce_adapter: BigCommerceAdapter,
        search_results: List[Any] = None  # New optional param
    ) -> Dict[str, Any]:
        
        # Step A: Query Pinecone (if search_results not provided)
        if search_results is None:
            # We assume org_id is used as namespace
            namespace = f"org_{org_id}"
            
            # Using asyncio.to_thread to run sync calls in a separate thread
            search_task = asyncio.to_thread(
                self.vector_service.similarity_search_with_score,
                query=current_ticket_body, 
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
        # Passing max_score to the system prompt generator to enforce the conditional logic
        # strictly at the prompt level.
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", self._get_system_prompt(max_score)),
            ("user", f"""
            Current Ticket Query: {current_ticket_body}
            
            Top Max Similarity Score: {max_score}
            
            Retrieved Context:
            {json.dumps(context_texts, indent=2)}
            
            Real-time Order Status:
            {json.dumps(order_status, indent=2)}
            """)
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
