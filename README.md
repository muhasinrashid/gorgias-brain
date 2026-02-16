# Universal Support Brain

## Overview
Universal Support Brain is a B2B SaaS RAG integration designed to provide intelligent support responses by leveraging historical data from Gorgias and web-based knowledge bases. It uses a Retrieval-Augmented Generation (RAG) approach to synthesize accurate, contextual answers.

## Architecture

### Tech Stack
- **Frontend**: Next.js (App Router) — Sidebar widget for Gorgias
- **Backend**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL (via Docker / Supabase / RDS)
- **Vector DB**: Pinecone (Serverless)
- **LLM**: Azure OpenAI (GPT-4o-mini + text-embedding-3-small)
- **Web Crawler**: Apify (website-content-crawler) with httpx fallback
- **Infrastructure**: Docker Compose for local dev (PostgreSQL, Redis)

### Core Components
- **Adapter Pattern**: Platform-agnostic interfaces for CRM (Gorgias) and future integrations (BigCommerce, Shopify).
- **Multi-Source Ingestion**: Historical tickets, web pages, and FAQ articles.
- **PII Scrubbing**: Sanitizes data before embedding and storage.

### Data Flow

1. **Ingestion** (Knowledge Base Building):
   - `POST /ingest/historical` — Fetches closed Gorgias tickets, extracts Q&A pairs, embeds and stores in Pinecone.
   - `POST /ingest/web` — Crawls a single URL via Apify, chunks content, and stores in Pinecone.
   - `POST /ingest/web/batch` — Crawls multiple URLs in one request (handles SPA pages with shared canonical URLs).

2. **Processing**:
   - **PII Scrubber**: Removes emails, phone numbers, and personal data.
   - **Embedding**: Azure OpenAI `text-embedding-3-small` for vectorization.
   - **Chunking**: `RecursiveCharacterTextSplitter` (1000 chars, 200 overlap).

3. **Storage**:
   - **Pinecone**: Namespaced vector storage (`org_{id}`).
   - **PostgreSQL**: Organization settings, integration configs, metadata.

4. **Inference** (Answer Generation):
   - `GET /v1/gorgias-widget` — Receives ticket context, retrieves relevant knowledge, generates AI response within 4.5s timeout.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/v1/gorgias-widget` | Gorgias HTTP widget — generates AI response for a ticket |
| `POST` | `/ingest/historical` | Ingest closed Gorgias tickets into knowledge base |
| `POST` | `/ingest/web` | Crawl and ingest a single web page |
| `POST` | `/ingest/web/batch` | Crawl and ingest multiple web pages |

All endpoints (except the widget) require `X-API-Key` header.

## Monorepo Structure

```
├── backend/
│   ├── adapters/         # Platform adapters (Gorgias, BigCommerce)
│   ├── routers/          # API endpoints (ingest, inference)
│   ├── services/         # Business logic (crawler, vector store, reasoning engine)
│   ├── tests/            # Unit tests
│   ├── config.py         # Settings & env var loading
│   ├── main.py           # FastAPI app setup
│   └── requirements.txt
├── frontend/             # Next.js sidebar widget
├── docker-compose.yml    # PostgreSQL + Redis
├── start.sh              # Development startup script
└── RELEASE_NOTES.md
```

## Setup

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Node.js & npm
- Apify account (for web crawling)

### Environment Variables
Create `backend/.env`:
```env
# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/universal_support_brain

# Security
ADMIN_API_KEY=your-admin-api-key

# Gorgias
GORGIAS_DOMAIN=your-store.gorgias.com
GORGIAS_API_KEY=your-gorgias-api-key
GORGIAS_EMAIL=your-email@example.com

# Azure OpenAI
AZURE_OPENAI_API_KEY=your-azure-key
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=gpt-4o-mini
AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME=text-embedding-3-small

# Pinecone
PINECONE_API_KEY=your-pinecone-key

# Apify
APIFY_API_KEY=your-apify-key
```

### Installation & Running
```bash
# Start infrastructure
docker-compose up -d

# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

### Running Tests
```bash
python3 -m pytest backend/tests/ -v
```

## Utility Scripts
| Script | Purpose |
|--------|---------|
| `trigger_ingest.py` | Trigger ingestion endpoints for testing |
| `trigger_ingest_test.py` | Integration test for ingestion pipeline |
| `verify_ingested.py` | Verify ingested data via Pinecone similarity search |
