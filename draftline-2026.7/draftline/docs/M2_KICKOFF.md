# M2 Kickoff — Knowledge Layer

**Started:** 2026-08-01 · **Closed:** 2026-08-02  
**Depends on:** M0 complete; M1 advanced with [open debt](M1_STATUS.md) (gate deferred).  
**Live team slug:** `test` (Formex)  
**Status doc:** [`M2_STATUS.md`](M2_STATUS.md)

## Goal

Turn ingested Sources + SUPPORT ticket threads into **retrievable knowledge**: chunks with embeddings (pgvector), **ResolutionPairs**, curated Q&A, hybrid retrieval with precedence.

```
CuratedKnowledge > Help Center / Web > ResolutionPair (recent, high quality)
                 > Macro (phrasing only) > Files
```

## Build slices

| # | Slice | Status |
|---|--------|--------|
| 1 | Infra — `pgvector/pgvector:pg17`, extension `vector` | **Done** |
| 2 | Models — `Chunk`, `ResolutionPair`, `CuratedKnowledge`, `IntentNode` | **Done** |
| 3 | Chunking — `chunk_sources` for WEB / HC / MACRO | **Done** |
| 4 | Embeddings — Azure `text-embedding-3-small` | **Done** |
| 5 | ResolutionPair extraction — SUPPORT + resolving; confidence floor | **Done** |
| 6 | Retrieval — hybrid + precedence + language + recency + quality | **Done** |
| 7 | Curated Knowledge UI — create / edit / de-id / approve / retire | **Done** |
| 8 | Eval harness — FAQ + mixed held-out; recall@5 + language match | **Done** |
| 9 | Intent taxonomy seed + `NOT_SUPPORT` | **Done** |
| 10 | Citations resolve + quarantine / FAQ crawl scope | **Done** |

## Commands

```bash
cd draftline-2026.7/draftline
uv run manage.py chunk_sources --team-slug test
uv run manage.py extract_resolution_pairs --team-slug test --limit 500
uv run manage.py embed_knowledge --team-slug test --chunks --pairs --sync
uv run manage.py seed_intent_taxonomy --team-slug test
uv run manage.py quarantine_web_noise --team-slug test
uv run manage.py retrieve_knowledge --team-slug test --query "return policy"
uv run manage.py eval_retrieval --team-slug test --mode faq --k 5
uv run manage.py eval_retrieval --team-slug test --mode mixed --limit 200 --k 5
```

## Done when (PRODUCT_SPEC) — closed 2026-08-02

- recall@5 ≥ 0.85 on held-out (FAQ mode green; see `M2_STATUS.md` for measured numbers)
- citations resolve
- language match ≥ 90%
- precedence demonstrable (weights + unit test)

**Next:** M3 · Commerce Grounding.
