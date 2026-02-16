# Gorgias Brain — Product Requirements Document

## Vision
An AI-powered Customer Support assistant that integrates with Gorgias to help CS teams answer customer questions faster and more accurately. The system ingests knowledge from multiple sources and uses RAG (Retrieval-Augmented Generation) to provide contextual, accurate suggested responses.

---

## Architecture Principles

### Pluggable Vendor Architecture
The system **must** be designed so that any vendor can be swapped out without refactoring core logic:

| Component | Current Vendor | Interface/Abstract Class |
|---|---|---|
| **Web Crawler** | Apify (`website-content-crawler`) | `BaseCrawler` |
| **Vector Database** | Pinecone (Serverless) | `BaseVectorStore` |
| **LLM** | Azure OpenAI (GPT-4o) | `BaseLLM` |
| **Embeddings** | Azure OpenAI Embeddings | `BaseEmbeddings` |
| **Cache** | Redis (planned) | `BaseCache` |

> **Rule:** Services should depend on abstract interfaces, not concrete implementations.

---

## Data Sources (Knowledge Ingestion)

The system accepts knowledge from multiple sources. Each source type has its own ingestion pipeline:

### 1. Website Pages (Web Crawler)
- **Input:** Any public website URL (FAQ pages, help centers, product pages, etc.)
- **Pipeline:** Crawl → Extract text → PII scrub → Chunk → Embed → Store in vector DB
- **Crawler must be generic:** Works on any website, not hardcoded to a specific domain
- **Handles:** Pop-ups, cookie banners, SPAs, iframes, dynamic content
- **Future:** Explore cost-effective alternatives to Apify (e.g., Playwright self-hosted, Crawlee)

### 2. Historical Tickets (Gorgias API)
- **Input:** Gorgias API credentials (subdomain, API key, email)
- **Pipeline:** Fetch closed tickets → Pair Q&A (customer question + agent resolution) → Filter noise (min 50 chars) → PII scrub → Chunk → Embed → Store
- **Quality:** Strictly pair customer questions with agent resolutions, exclude automated messages, "Thank you" responses, etc.

### 3. Product Information (BigCommerce API) — *Planned*
- **Input:** BigCommerce API credentials
- **Pipeline:** Fetch products/catalog → Extract descriptions, specs, pricing → Chunk → Embed → Store
- **Use case:** Answer product-specific questions (sizing, materials, availability)

### 4. Documents & Files — *Planned*
- **Input:** PDF, DOCX, TXT uploads
- **Pipeline:** Parse document → Extract text → Chunk → Embed → Store
- **Use case:** Internal SOPs, policies, training materials

### 5. YouTube Videos — *Planned*
- **Input:** YouTube URL
- **Pipeline:** Fetch transcript (via YouTube API) → Chunk → Embed → Store
- **Use case:** Product demos, how-to guides, brand videos

### 6. Custom Knowledge Base — *Planned*
- **Input:** Manual Q&A pairs entered by the user
- **Pipeline:** Direct embed → Store
- **Use case:** Brand-specific answers, edge cases, corrections

---

## End Product — User Flows

### Onboarding Flow
1. **Create Account** → Organization setup
2. **Connect Gorgias** → API key, subdomain, email
3. **Connect BigCommerce** → API credentials (optional)
4. **Add Website URLs** → FAQ pages, help center, product pages
5. **Upload Documents** → PDFs, docs (optional)
6. **Add YouTube Links** → (optional)
7. **Trigger Initial Ingestion** → System processes all sources
8. **Install Gorgias Widget** → HTTP integration URL provided

### CS Agent Experience (Gorgias Sidebar)
1. Agent opens a ticket in Gorgias
2. Sidebar widget loads automatically
3. System retrieves similar past tickets + relevant knowledge
4. AI generates a suggested response
5. Agent reviews, edits, and pushes to draft
6. Feedback loop logs quality for continuous improvement

---

## Current Implementation Status (v0.1 MVP)

### ✅ Delivered
- [x] FastAPI backend with PostgreSQL
- [x] Gorgias HTTP Widget endpoint (`/v1/gorgias-widget`)
- [x] RAG engine with Azure OpenAI + Pinecone
- [x] Historical ticket ingestion (`/ingest/historical`)
- [x] Web page ingestion (`/ingest/web`) — basic, Apify-powered
- [x] PII scrubbing
- [x] Dynamic timeout manager (4.5s for Gorgias compliance)
- [x] Sidebar widget (Next.js)
- [x] Railway deployment (Docker)

### 🔧 In Progress (v0.2)
- [ ] **Web Crawler tuning** — Handle pop-ups, SPAs, iframes generically
- [ ] **Data quality** — Better Q&A pairing from tickets, noise filtering
- [ ] **Pluggable architecture** — Abstract interfaces for crawler, vector store, LLM

### 📋 Planned (v0.3+)
- [ ] BigCommerce product ingestion
- [ ] Document upload ingestion (PDF, DOCX)
- [ ] YouTube transcript ingestion
- [ ] Redis caching for frequent queries
- [ ] Onboarding flow UI
- [ ] Multi-org / multi-tenant support
- [ ] Feedback loop & analytics dashboard
- [ ] Custom Q&A pair entry
- [ ] Scheduled re-ingestion (cron for fresh data)

---

## Technical Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python 3.14) |
| Frontend | Next.js (React) |
| Database | PostgreSQL |
| Vector Store | Pinecone (Serverless) |
| LLM | Azure OpenAI (GPT-4o) |
| Embeddings | Azure OpenAI Embeddings |
| Web Crawler | Apify (website-content-crawler) |
| PII Scrubbing | Custom regex-based |
| Deployment | Railway (Docker) |
| Cache | Redis (planned) |

---

## Environment Variables

```
# Gorgias
GORGIAS_DOMAIN=
GORGIAS_API_KEY=
GORGIAS_EMAIL=

# Azure OpenAI
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_DEPLOYMENT=
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=
AZURE_OPENAI_API_VERSION=

# Pinecone
PINECONE_API_KEY=
PINECONE_INDEX=

# Apify
APIFY_API_KEY=

# Database
DATABASE_URL=

# Redis (planned)
REDIS_URL=
```
