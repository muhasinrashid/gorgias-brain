import os
import asyncio
from dotenv import load_dotenv
from pinecone import Pinecone
from langchain_openai import OpenAIEmbeddings, AzureOpenAIEmbeddings

load_dotenv('backend/.env')

# Initialize Pinecone
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("universal-support-brain")

# Initialize Embeddings
if os.getenv("AZURE_OPENAI_API_KEY"):
    print("Using Azure OpenAI Embeddings...")
    embeddings = AzureOpenAIEmbeddings(
        model=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-small"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    )
else:
    print("Using Standard OpenAI Embeddings...")
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )

query = "What is the return policy?"
print(f"\nrunning search for: '{query}'...\n")

vector = embeddings.embed_query(query)

results = index.query(
    namespace="org_1",
    vector=vector,
    top_k=5,
    include_metadata=True
)

if not results['matches']:
    print("❌ No matches found! Ingestion might have failed completely.")
else:
    print(f"✅ Found {len(results['matches'])} matches:\n")
    for match in results['matches']:
        meta = match['metadata']
        text = meta.get('text', 'No text found')
        score = match['score']
        source_id = meta.get('source_id', '?')
        source_type = meta.get('source_type', 'unknown')
        source_url = meta.get('source_url', '')
        mode = meta.get('extraction_mode', '')
        print(f"--- [{source_type}] Score: {score:.4f} ---")
        print(f"  Source: {source_url or source_id}")
        if mode:
            print(f"  Mode: {mode}")
        print(text[:500] + "..." if len(text) > 500 else text)
        print()
