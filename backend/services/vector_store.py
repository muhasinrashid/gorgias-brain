import os
import time
import uuid
from typing import List, Dict, Any, Optional, Tuple
from langchain_openai import OpenAIEmbeddings, AzureOpenAIEmbeddings
from langchain_core.documents import Document
from pinecone import Pinecone, ServerlessSpec

class VectorService:
    def __init__(self, index_name: str = "universal-support-brain"):
        self.api_key = os.getenv("PINECONE_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.index_name = index_name
        
        if not self.api_key:
            # In production, we'd log a warning or error, but here we'll assume env vars will be set
            pass

        self.pc = Pinecone(api_key=self.api_key)
        
        # Initialize index if it doesn't exist
        try:
            existing_indexes = [index.name for index in self.pc.list_indexes()]
        except Exception:
            # Fallback or empty if list fails (though v3 should work)
            existing_indexes = []

        if self.index_name not in existing_indexes:
            print(f"Creating index: {self.index_name}")
            self.pc.create_index(
                name=self.index_name,
                dimension=1536, # text-embedding-3-small dimension
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
            # Wait a moment for index to be ready
            time.sleep(5)

        self.index = self.pc.Index(self.index_name)

        if os.getenv("AZURE_OPENAI_API_KEY"):
            self.embeddings = AzureOpenAIEmbeddings(
                model=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-small"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
            )
        else:
            self.embeddings = OpenAIEmbeddings(
                model="text-embedding-3-small",
                openai_api_key=self.openai_api_key
            )
        
    def embed_and_store(self, texts: List[str], metadatas: List[Dict[str, Any]], namespace: str):
        """
        Embeds texts using OpenAI and stores them in Pinecone with metadata.
        Adds a 'unix_timestamp' to metadata for temporal decay.
        Uses batching and retries to handle Azure OpenAI Rate Limits.
        """
        if not texts:
            return

        current_time = int(time.time())
        
        # Batch size for embedding to avoid Rate Limits (Azure S0 tier is sensitive)
        batch_size = 10 
        total_batches = (len(texts) + batch_size - 1) // batch_size
        
        print(f"Starting ingestion of {len(texts)} items in {total_batches} batches...")
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            batch_metadatas = metadatas[i : i + batch_size]
            
            # Retry logic for embedding
            max_retries = 5
            embeddings = []
            for attempt in range(max_retries):
                try:
                    embeddings = self.embeddings.embed_documents(batch_texts)
                    break
                except Exception as e:
                    if "429" in str(e) or "RateLimit" in str(e):
                        wait_time = (2 ** attempt) * 5  # 5s, 10s, 20s, 40s, 80s
                        print(f"Rate limit hit on batch {i//batch_size + 1}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        print(f"Error embedding batch: {e}")
                        raise e
            
            if not embeddings:
                print(f"Skipping batch {i//batch_size + 1} due to embedding failure.")
                continue

            # Prepare vectors
            vectors_to_upsert = []
            
            for j, (text, meta, vector) in enumerate(zip(batch_texts, batch_metadatas, embeddings)):
                full_metadata = meta.copy()
                full_metadata['unix_timestamp'] = current_time
                # LangChain convention: store text in metadata 'text' field
                full_metadata['text'] = text
                
                # Use source_id if available as ID, otherwise random UUID
                item_id = str(full_metadata.get('source_id', uuid.uuid4()))
                
                vectors_to_upsert.append({
                    "id": item_id,
                    "values": vector,
                    "metadata": full_metadata
                })

            # Upsert to Pinecone
            try:
                self.index.upsert(vectors=vectors_to_upsert, namespace=namespace)
                print(f"Upserted batch {i//batch_size + 1}/{total_batches}")
            except Exception as e:
                print(f"Error upserting to Pinecone: {e}")
            
            # Small buffer between batches
            time.sleep(1)

    def similarity_search(self, query: str, k: int = 5, namespace: str = None) -> List[Document]:
        query_vector = self.embeddings.embed_query(query)
        results = self.index.query(
            namespace=namespace,
            vector=query_vector,
            top_k=k,
            include_metadata=True
        )
        
        documents = []
        for match in results['matches']:
            metadata = match['metadata'] if 'metadata' in match else {}
            text = metadata.pop('text', '') # Extract text from metadata
            doc = Document(page_content=text, metadata=metadata)
            documents.append(doc)
            
        return documents

    def similarity_search_with_score(self, query: str, k: int = 3, namespace: str = None) -> List[Tuple[Document, float]]:
        """Returns documents and their similarity scores."""
        query_vector = self.embeddings.embed_query(query)
        results = self.index.query(
            namespace=namespace,
            vector=query_vector,
            top_k=k,
            include_metadata=True
        )
        
        docs_with_scores = []
        for match in results['matches']:
            metadata = match['metadata'] if 'metadata' in match else {}
            text = metadata.pop('text', '')
            score = match['score']
            doc = Document(page_content=text, metadata=metadata)
            docs_with_scores.append((doc, score))
            
        return docs_with_scores
