# M2 Kickoff — Knowledge Layer

**Started:** 2026-08-01 · **In progress:** 2026-08-02  
**Depends on:** M0 complete; M1 advanced with [open debt](M1_STATUS.md) (gate deferred).  
**Live team slug:** `test` (Formex)

## Goal

Turn ingested Sources + SUPPORT ticket threads into **retrievable knowledge**: chunks with embeddings (pgvector), **ResolutionPairs**, curated Q&A, hybrid retrieval with precedence.

```
CuratedKnowledge > Help Center / Web > ResolutionPair (recent, high quality)
                 > Macro (phrasing only) > Files
```

## Build slices

| # | Slice | Status |
|---|--------|--------|
| 1 | Infra — `pgvector/pgvector:pg17`, extension `vector` | Done |
| 2 | Models — `Chunk`, `ResolutionPair`, `CuratedKnowledge` | Done |
| 3 | Chunking — `chunk_sources` for WEB / HC / MACRO | Done |
| 4 | Embeddings — Azure `text-embedding-3-small`; `knowledge.embed_chunks` / `embed_resolution_pairs` | **Done (2026-08-02)** |
| 5 | ResolutionPair extraction — SUPPORT + resolving reply; confidence floor | **Done (2026-08-02)** |
| 6 | Retrieval stub — hybrid lexical + vector, precedence, citations | **Done (2026-08-02)** |
| 7 | Curated Knowledge UI — DRAFT → APPROVED → RETIRED | Next |
| 8 | Eval harness — held-out 200 questions; recall@5 | Next |

## Commands

```bash
cd draftline-2026.7/draftline
# Chunk active sources
uv run manage.py chunk_sources --team-slug test

# Resolution pairs (prefers confidence ≥0.8 or null + resolving reply)
uv run manage.py extract_resolution_pairs --team-slug test --limit 500

# Embed (requires Azure OpenAI env; --sync runs inline)
uv run manage.py embed_knowledge --team-slug test --chunks --pairs --sync --limit 100

# Smoke retrieval
uv run manage.py retrieve_knowledge --team-slug test --query "return policy"
```

## Constraints while M1 debt is open

- Prefer high-confidence SUPPORT + `is_resolving_reply` (TD-M1-01 still open).
- Web pages are available (~32); macros land after Gorgias ticket pass auto-chains.
- Never embed customer-send paths; knowledge is for drafting only (M4).

## Done when (PRODUCT_SPEC)

recall@5 ≥ 0.85 on 200 held-out · citations resolve · language match ≥90% · precedence demonstrable.
