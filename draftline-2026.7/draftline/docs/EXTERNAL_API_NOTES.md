# External API Notes

Hard-won knowledge extracted from the Universal Support Brain POC (`Gorgias.0.1` / [gorgias-brain](https://github.com/muhasinrashid/gorgias-brain.git)). Re-verify against live docs before treating as permanent truth. Update this file when an API surprises you.

## Gorgias

### Auth
- Private apps: HTTP Basic with `username:api_key` (base64). Username is typically the integration email.
- POC env vars: `GORGIAS_USERNAME`, `GORGIAS_API_KEY`, `GORGIAS_BASE_URL` (e.g. `https://formexwatch.gorgias.com`).

### Message sender classification
- **`sender.type` is always `"unknown"`** in observed responses. Do not use it to distinguish customer vs agent.
- Use the boolean **`from_agent`** as the primary classifier. Fall back to `sender.type` only if needed.

### Ticket list filtering
- List endpoint does **not** reliably support server-side `status=closed` filtering in the way we expected. POC pattern: over-fetch (`limit * 3`), filter `status == "closed"` in application code.
- Max page size observed: **100**. Pagination via `meta.next_cursor`.

### Messages endpoint shape
- `GET /api/tickets/{id}/messages` may return `{ "data": [...] }` **or** a bare list. Handle both.

### Internal notes (highest-risk surface)
- `POST /api/tickets/{ticket_id}/messages` with:
  ```json
  {
    "channel": "internal-note",
    "via": "api",
    "from_agent": true,
    "body_text": "...",
    "sender": { "email": "<integration-username>" }
  }
  ```
- Creation and sending are decoupled in Gorgias; empty `sent_datetime` can trigger async send on other channels. **Never** assemble a customer-visible channel payload. One function, one payload shape, fully tested.
- Accept only HTTP 200/201 as success; log response body on failure.

### HTTP Integrations / webhooks
- Events: ticket created / updated / message added.
- **5-second timeout**, 3 retries at 10s / 20s / 40s.
- Acknowledge in under **500ms**. Do not run drafting synchronously in the webhook handler.
- Idempotency is mandatory: retries must not produce a second draft.

### Widget timeout workaround
- Docs/PRD mentioned a 4.5s sync generation timeout. The working pattern is: return an immediate ack (`{"type":"text","text":"…"}`), then generate in a background task and post an **internal note**.
- Loop prevention: if the latest message on the ticket is already from an agent, abort note creation (avoid feedback loops when our note triggers `message_added`).

### Rate limits
- Unverified officially. POC used `time.sleep(0.3)` between ticket hydrations and treated the API gently. Establish empirically before designing production backfill pacing.

### Useful endpoints used in POC
- `GET /api/tickets?limit=1` — **preferred health / auth probe** (200 = credentials work)
- ~~`GET /api/users/me`~~ — returns **400** `"pk is not a valid integer"` on current API; do not use for health checks
- `GET /api/tickets` — list (cursor)
- `GET /api/tickets/{id}` — detail
- `GET /api/tickets/{id}/messages` — thread
- `POST /api/tickets/{id}/messages` — internal note only
- `GET /api/macros` — macros (supports `order_by=usage:desc`, cursor pagination). Formex: ~1062 macros.
- `GET /api/help-centers` then `GET /api/help-centers/{id}/articles` — documented Help Center flow. **Formex (`formexwatch.gorgias.com`) returns 404** on `/api/help-centers` (account may not have native HC / API not enabled). Treat as optional; use **website crawl** for FAQ knowledge.

## Apify (website crawl) — platform-owned

- Draftline holds **one** Apify account; tenants never supply keys. Configured via SaaS admin `PlatformCrawlerSettings` (encrypted API key + actor id).
- Preferred actor: custom **Draftline web crawler** (built in a separate project). Until that ships, admin may point at `apify/website-content-crawler`.
- Input contract for the custom actor: `startUrls`, `maxCrawlDepth`, `maxCrawlPages`, `sameOriginOnly`, `includeUrlPatterns`.
- **Canonical / SPA rule (Formex):** page identity must keep query params (`?hcUrl=`). Stock actor needs `useCanonicalUrl: True` + `keepUrlFragment: True` or pages collapse.
- Fallback: httpx + BeautifulSoup when Apify key/actor missing or run fails.
- Formex FAQ seeds: `https://formexwatch.com/faqs/` and `?hcUrl=` article URLs (see `ingest_formex_full.py`).

## Azure OpenAI / embeddings

- Embedding model: `text-embedding-3-small`, dim **1536**.
- Batch size **10** with exponential backoff on 429: **5s, 10s, 20s, 40s, 80s**; ~1s pause between batches.
- Chat: temperature `0` for drafting consistency.
- LangChain prompt templates: escape `{` / `}` in ticket HTML or template parsing breaks.
- Prefer API-reported `token_usage` over local token estimators when available.

## Pinecone (POC only — Draftline uses pgvector)

- Index name in POC: `universal-support-brain`, cosine, serverless `us-east-1`.
- Namespace: `org_{org_id}`.
- Vector ID = natural `source_id` for idempotent upsert.
- Metadata stores full chunk `text` plus `unix_timestamp` for recency boosting.

## Draftline mapping

| POC | Draftline |
|-----|-----------|
| Pinecone namespaces | Postgres `pgvector` + team FK (M2) |
| FastAPI `/v1/gorgias-widget` background note | Celery `drafting` queue + `InternalNoteDelivery` (M4) |
| Env-based Gorgias creds | Encrypted `Connection` credentials per team (M0/M1) |
| Org id hardcoded `1` | `Team` tenancy |
