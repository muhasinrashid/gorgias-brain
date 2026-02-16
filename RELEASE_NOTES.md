# Release Notes

## v0.2 — Ingestion & Crawler Fixes (2026-02-16)

### Status: 🟢 Ready for Production

**Deployment URL:** `https://gorgias-brain-production.up.railway.app`
**Platform:** Railway (Dockerized FastAPI + PostgreSQL)
**Vector Database:** Pinecone (Serverless)
**LLM:** Azure OpenAI (GPT-4o-mini / text-embedding-3-small)

### Bug Fixes

#### 🔧 Fix: Historical Ticket Ingestion — "No valid text content found"
**Root Causes (4 bugs):**
1. **Sender detection broken** — `sender.type` is always `"unknown"` in Gorgias API. Fixed to use `from_agent` (boolean) as primary detection.
2. **Q&A pairing too strict** — Required both customer question (≥50 chars) AND agent resolution (≥50 chars). Most closed tickets are single-message. Added 3 extraction modes.
3. **No HTML fallback** — Some messages only have `body_html`, not `body_text`. Added `body_text → stripped_text → strip(body_html)` fallback chain.
4. **Insufficient ticket fetching** — Only fetched `limit` raw tickets, but most aren't closed or are noise. Now fetches `limit × 3`.

**Result:** 0 tickets → **10 tickets ingested** (3 Q&A pairs + 1 agent-only + 6 subject+content)

#### 🔧 Fix: Web Crawler — Canonical URL Deduplication Skipping
**Root Cause:** Apify's `useCanonicalUrl` flag has inverted semantics:
- `False` (what we had) = **uses** canonical URLs for dedup → pages skipped
- `True` (what we need) = **ignores** canonical URLs → each URL crawled independently

**Result:** FAQ pages with query params (`?hcUrl=...`) now crawl successfully.

#### 🔧 Fix: `.env` Loading Path
`load_dotenv()` was relative to CWD. Fixed to resolve `.env` relative to `config.py`'s own directory.

### New Features

#### 📦 Three Knowledge Extraction Modes
Tickets are now processed through three quality tiers:
1. **Full Q&A Pair** — Customer question + agent resolution (highest quality)
2. **Agent-Only Resolution** — Meaningful agent response without clear customer question
3. **Subject + Content** — Single-message tickets paired with ticket subject

#### 🌐 Batch Web Ingestion Endpoint
`POST /ingest/web/batch` — Crawl multiple URLs in one request:
```json
{
    "urls": [
        "https://example.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Freturns-154421",
        "https://example.com/faqs/?hcUrl=%2Fen-US%2Farticles%2Fshipping-154418"
    ],
    "org_id": 1
}
```

#### 🧪 Comprehensive Crawler Tests
12 unit tests covering Apify config, fallback crawler, chunking, and edge cases.

### Files Changed
| File | Change |
|------|--------|
| `backend/routers/ingest.py` | Rewrote ticket ingestion + added `/web/batch` endpoint |
| `backend/services/crawler.py` | Fixed `useCanonicalUrl: True`, added `keepUrlFragment: True` |
| `backend/config.py` | Fixed `.env` path resolution |
| `backend/tests/test_crawler_logic.py` | New: 12 unit tests for crawler |

---

## v0.1 — MVP (Initial Release)

### Features Delivered
- **Gorgias Integration:** HTTP Widget endpoint (`/v1/gorgias-widget`) connected to live ticket context.
- **RAG Engine:** Retrieves similar past tickets to answer new customer queries.
- **Dynamic Timeout Manager:** Enforces a hard 4.5s limit to comply with Gorgias widget requirements.
- **Ingestion Pipeline:** Basic historical ticket ingestion (`/ingest/historical`).
- **Noise Fallback:** Returns raw search results if AI generation is skipped due to time constraints.

### Usage
**Gorgias HTTP URL:**
```
https://gorgias-brain-production.up.railway.app/v1/gorgias-widget?ticket_id={{ticket.id}}&subject={{ticket.subject}}&body_text={{ticket.first_message.body_text}}&customer_email={{ticket.customer.email}}
```
