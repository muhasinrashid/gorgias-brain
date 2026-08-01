# M2 Kickoff — Knowledge Layer

**Started:** 2026-08-01  
**Depends on:** M0 complete; M1 advanced with [open debt](M1_STATUS.md) (gate deferred).

## Goal

Turn ingested Sources + SUPPORT ticket threads into **retrievable knowledge**: chunks with embeddings (pgvector), **ResolutionPairs**, curated Q&A, hybrid retrieval with precedence.

```
CuratedKnowledge > Help Center / Web > ResolutionPair (recent, high quality)
                 > Macro (phrasing only) > Files
```

## First build slices (order)

1. **Infra** — Postgres image with `pgvector`; `CREATE EXTENSION vector`; Django vector field on `Chunk`.
2. **Models** — `Chunk`, `ResolutionPair`, `CuratedKnowledge` (+ migrations), team-scoped.
3. **Chunking** — text splitters for `Source` WEB_PAGE / HELP_CENTER / MACRO (macros → phrasing metadata, not facts); ticket resolving pairs separately.
4. **Embeddings** — Azure OpenAI `text-embedding-3-small` (1536-d) behind an adapter; Celery `knowledge.embed_chunks`.
5. **ResolutionPair extraction** — from SUPPORT tickets with `is_resolving_reply`; skip autoresponders.
6. **Retrieval stub** — hybrid lexical + vector, team-scoped, precedence weights; citation returns `source_id` + offsets.
7. **Curated Knowledge UI** — DRAFT → APPROVED (de-id required) → RETIRED.
8. **Eval harness** — held-out 200 questions; recall@5 gate.

## Constraints while M1 debt is open

- Do not treat all SUPPORT as clean until TD-M1-01; filter `qualification_confidence` and resolving-reply.
- Do not block M2 scaffolding on Apify; web chunks land when TD-M1-02 closes.
- Never embed customer-send paths; knowledge is for drafting only (M4).

## Infra note (local)

`docker-compose.yml` uses `pgvector/pgvector:pg17`. If you already had a plain `postgres:17` volume, recreate once:

```bash
docker compose down
# WARNING: destroys local DB data
docker volume rm draftline_postgres_data   # name may vary: docker volume ls | grep postgres
docker compose up -d
uv run manage.py migrate
```

Or keep data and install extension only if the image already supports it (pgvector image required).
