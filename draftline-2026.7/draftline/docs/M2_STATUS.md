# M2 Status — Knowledge Layer

**Status:** Scaffold + core path working; **PRODUCT_SPEC gate not closed** (Curated UI + recall@5 still open).  
**Updated:** 2026-08-02  
**Team:** `test` (Formex)  
**Vector store:** PostgreSQL **pgvector** (same DB as Draftline) — not Pinecone  
**Embedder:** Azure OpenAI `text-embedding-3-small` (1536-d) → `Chunk.embedding` / `ResolutionPair.embedding`

---

## Snapshot (team `test`)

| Metric | Value |
|--------|------:|
| Web `Source` pages | 32 |
| Chunks | 141 (**40** embedded in smoke) |
| ResolutionPairs | 197 (**40** embedded in smoke) |
| CuratedKnowledge UI | not built |
| recall@5 eval | not built |
| Local retrieve smoke (`return policy`, 5 runs) | p50 ~1.1s (dominated by Azure query embed ~1.7s cold / ~1.1s warm); 5/5 hits; top hit Formex returns FAQ |

---

## Delivered

1. pgvector infra + models (`Chunk`, `ResolutionPair`, `CuratedKnowledge`)
2. Chunking (`chunk_sources`)
3. Embeddings jobs + `embed_knowledge`
4. ResolutionPair extraction (`extract_resolution_pairs`) with SUPPORT confidence floor
5. Hybrid retrieval stub (`retrieve` / `retrieve_knowledge`) with precedence + citation offsets
6. Efficiency smoke (`benchmark_retrieval`)

## Still open (blocks “M2 done”)

- **TD-M2-01** Curated Knowledge UI (DRAFT → APPROVED de-id → RETIRED)
- **TD-M2-02** Held-out eval set (~200 Qs) + recall@5 ≥ 0.85
- **TD-M2-03** Full corpus embed (all chunks + pairs); optional HNSW index if latency grows
- **TD-M2-04** Language-match measurement ≥90%

---

## How to test embeddings + efficiency

```bash
cd draftline-2026.7/draftline

# 1) Ensure chunks / pairs exist
uv run manage.py chunk_sources --team-slug test
uv run manage.py extract_resolution_pairs --team-slug test --limit 500

# 2) Embed (inline; omit --limit to do all missing)
uv run manage.py embed_knowledge --team-slug test --chunks --pairs --sync

# 3) Qualitative retrieval smoke
uv run manage.py retrieve_knowledge --team-slug test --query "return policy" --limit 5
uv run manage.py retrieve_knowledge --team-slug test --query "shipping time" --limit 5

# 4) Latency / coverage benchmark
uv run manage.py benchmark_retrieval --team-slug test --query "return policy" --runs 5
```

**What “good” looks like for this slice**
- Coverage: embedded counts rise toward totals
- Retrieval: top hit for FAQ-ish queries is a WEB_PAGE chunk or ResolutionPair with `source_id` + offsets
- Efficiency (local smoke): query embed usually ~100–400ms (Azure RTT); retrieve p50 under ~1s on this corpus size is fine — Spec p95 draft assembly &lt;3s is an M3/M4 concern

Unit tests: `uv run manage.py test apps.knowledge.tests.test_m2_knowledge`

---

## Decision

Treat M2 as **in progress** on the core retrieve path. Do not mark PART 6 gate closed until TD-M2-01/02 land. Continue Curated UI + eval next.
