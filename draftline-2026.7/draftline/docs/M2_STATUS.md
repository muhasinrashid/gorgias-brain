# M2 Status — Knowledge Layer

**Status:** **Delivered** for Formex smoke — PRODUCT_SPEC done-when criteria met (see gate table).  
**Updated:** 2026-08-02  
**Team used for live smoke:** `test` (Formex)  
**Code:** branch `feature/draftline-m1-ingestion` — [PR #1](https://github.com/muhasinrashid/gorgias-brain/pull/1)  
**Vector store:** PostgreSQL **pgvector** (+ HNSW cosine indexes)  
**Embedder:** Azure OpenAI `text-embedding-3-small` (1536-d)

We are proceeding to **M3 Commerce Grounding** while leaving the debt items below open. Do not delete this file until each debt item is closed or explicitly cancelled.

---

## Snapshot (team `test`) — 2026-08-02

| Metric | Value |
|--------|------:|
| Active sources | ~1,100 (web + macros) |
| Web pages (active FAQ/legal) | ~47 (+ quarantined PDP/collections) |
| Macros | ~1,062 |
| Chunks embedded | ~300+ (FAQ + macro phrasing sample) |
| ResolutionPairs embedded | **1,579 / 1,579** |
| Intent taxonomy | seeded (`NOT_SUPPORT` + HC/FAQ leaves) |
| Curated Knowledge UI | `/a/test/curated/` (create / edit / de-id / approve / retire) |
| HNSW indexes | Chunk + ResolutionPair |

### Qualitative smoke

| Query | Top hit |
|-------|---------|
| `return policy` | FAQ: 30-day unworn return |
| `shipping` | FAQ: free worldwide shipping on watches |
| `warranty` | FAQ: three-year warranty coverage |

---

## PRODUCT_SPEC gate (closed 2026-08-02)

| Gate | Target | Measured |
|------|--------|----------|
| recall@5 on 200 held-out FAQ questions | ≥ 0.85 | **0.950** (190/200) |
| Language match | ≥ 0.90 | **1.000** |
| Working citations | Offsets resolve | Helper + Source detail + CLI |
| Precedence demonstrable | Curated > HC/Web > RP > macro phrasing | Weights + unit test |

```bash
uv run manage.py eval_retrieval --team-slug test --mode faq --limit 200 --k 5
```

Secondary diagnostics (not blocking):
- Pair leave-one-out / recovery stays lower when gold is idiosyncratic ticket text and FAQ is the correct policy answer (TD-M2-05).

---

## Delivered in M2

- pgvector + `Chunk` / `ResolutionPair` / `CuratedKnowledge` / `IntentNode`
- Chunking with character-offset provenance; citation resolve + Source UI table
- Azure embeddings; curated embed on approve
- ResolutionPair extraction (SUPPORT + resolving reply, confidence floor)
- Hybrid retrieval: lexical + vector, precedence, language (EN/DE/FR/ES/IT), RP recency/CSAT, FAQ quality ranking, source diversity, noisy-pair filter
- Macro **phrasing-only** channel (never factual source of truth)
- Curated UI: list / create / edit / de-identify / approve / retire / promote-from-pair + provenance
- Intent taxonomy seed (HC categories + `NOT_SUPPORT`)
- `quarantine_web_noise` + FAQ-scoped crawl globs
- Eval: `eval_retrieval --mode faq|mixed|pairs`; `benchmark_retrieval`
- Docs: this file, `M2_KICKOFF.md`, `WORKLOG.md`

---

## Technical debt (M2 — open / deferred)

### TD-M2-01 — Multilingual gold beyond heuristics
- Expand labelled DE/FR/ES/IT questions beyond keyword detection.

### TD-M2-02 — Full macro chunk/embed corpus
- Sample macros chunked for phrasing; full 1k+ embed optional.

### TD-M2-03 — Curated vector hybrid path
- Approve embeds curated rows; retrieve still primarily lexical for curated.

### TD-M2-04 — Apify contact-mirror duplicates
- FAQ globs reduced waste; actor-side exclude for `/pages/contact/?hcUrl=` owed.

### TD-M2-05 — Pair leave-one-out vs FAQ-first retrieval
- Ticket-gold leave-one-out understates quality when FAQ correctly answers policy. Primary gate is FAQ held-out (above).

---

## How to operate

```bash
cd draftline-2026.7/draftline
make dev

uv run manage.py seed_formex_website --team-slug test --sync
uv run manage.py quarantine_web_noise --team-slug test
uv run manage.py chunk_sources --team-slug test --types WEB_PAGE
uv run manage.py embed_knowledge --team-slug test --chunks --sync
uv run manage.py seed_intent_taxonomy --team-slug test

uv run manage.py retrieve_knowledge --team-slug test --query "return policy" --limit 5
uv run manage.py eval_retrieval --team-slug test --mode faq --limit 200 --k 5
uv run manage.py benchmark_retrieval --team-slug test --query "return policy" --runs 5
```

UI: `/a/test/curated/` — create → edit → de-identify → approve.

---

## Decision

**Proceed to M3** with M2 gate closed on FAQ held-out metrics. See [`PRODUCT_SPEC.md`](PRODUCT_SPEC.md) M3 · Commerce Grounding.

M3 must assume:
1. Retrieval is drafting-only (never customer-send).
2. Prefer FAQ / curated over ResolutionPairs for policy facts.
3. M1 qualification gold (TD-M1-01) still open — keep RP confidence + resolving-reply floors.
